import createDecoderModule from "./imm-web-decoder.mjs";
import { packPaintGeometry } from "./imm-web-geometry.mjs";


const SUMMARY_SIZE = 72;
const ERROR_SIZE = 176;
const ERROR_MESSAGE_OFFSET = 16;
const ERROR_MESSAGE_CAPACITY = 160;
const MAX_WASM32_SOURCE_SIZE = 0xffff_ffff;
const LAYER_INFO_SIZE = 280;
const LAYER_NAME_OFFSET = 24;
const LAYER_NAME_CAPACITY = 256;
const TRANSFORM_SIZE = 36;
const ANIMATION_INFO_SIZE = 16;
const STROKE_INFO_SIZE = 40;
const STROKE_POINT_SIZE = 56;
const STROKE_POINT_FLOATS = STROKE_POINT_SIZE / Float32Array.BYTES_PER_ELEMENT;
const PICTURE_INFO_SIZE = 28;
const SOUND_INFO_SIZE = 64;
const PLAYBACK_INFO_SIZE = 32;
const TIMELINE_LAYER_INFO_SIZE = 296;
const TIMELINE_LAYER_NAME_OFFSET = 40;
const ANIMATION_KEY_SIZE = 80;
const CHAPTER_INFO_SIZE = 24;
const KEEP_ALIVE_INFO_SIZE = 32;

let decoder;
let stagedSourcePointer = 0;
const decoderReady = createDecoderModule().then((module) => {
    decoder = module;
    return module;
});


function readSummary(memory, pointer) {
    return {
        schemaVersion: memory.getUint32(pointer, true),
        formatVersion: memory.getUint32(pointer + 4, true),
        sourceSize: memory.getBigUint64(pointer + 8, true),
        chunkCount: memory.getUint32(pointer + 16, true),
        chunkFlags: memory.getUint32(pointer + 20, true),
        sequenceType: memory.getUint32(pointer + 24, true),
        sequenceCapabilities: memory.getUint32(pointer + 28, true),
        sequenceOffset: memory.getBigUint64(pointer + 32, true),
        sequenceSize: memory.getBigUint64(pointer + 40, true),
        resourceTableOffset: memory.getBigUint64(pointer + 48, true),
        resourceTableSize: memory.getBigUint64(pointer + 56, true),
        assetCount: memory.getUint32(pointer + 64, true),
    };
}


function readError(memory, pointer) {
    const status = memory.getUint32(pointer, true);
    const byteOffset = memory.getBigUint64(pointer + 8, true);
    const bytes = Uint8Array.from(decoder.HEAPU8.subarray(
        pointer + ERROR_MESSAGE_OFFSET,
        pointer + ERROR_MESSAGE_OFFSET + ERROR_MESSAGE_CAPACITY,
    ));
    const terminator = bytes.indexOf(0);
    const messageBytes = terminator >= 0 ? bytes.subarray(0, terminator) : bytes;
    return {
        status,
        byteOffset,
        message: new TextDecoder().decode(messageBytes),
    };
}


function inspect(source) {
    if (!(source instanceof ArrayBuffer)) {
        throw new TypeError("inspect requires an ArrayBuffer");
    }
    if (source.byteLength > MAX_WASM32_SOURCE_SIZE) {
        throw new RangeError("IMM source exceeds the Wasm32 address space");
    }

    const sourcePointer = decoder._malloc(source.byteLength);
    const summaryPointer = decoder._malloc(SUMMARY_SIZE);
    const errorPointer = decoder._malloc(ERROR_SIZE);
    try {
        decoder.HEAPU8.set(new Uint8Array(source), sourcePointer);
        const status = decoder._imm_web_inspect(
            sourcePointer,
            source.byteLength,
            summaryPointer,
            errorPointer,
        );
        const memory = new DataView(decoder.HEAPU8.buffer);
        if (status !== 0) {
            return { ok: false, error: readError(memory, errorPointer) };
        }
        return { ok: true, summary: readSummary(memory, summaryPointer) };
    } finally {
        decoder._free(errorPointer);
        decoder._free(summaryPointer);
        decoder._free(sourcePointer);
    }
}


function readTransform(memory, pointer) {
    return {
        rotation: [
            memory.getFloat32(pointer, true),
            memory.getFloat32(pointer + 4, true),
            memory.getFloat32(pointer + 8, true),
            memory.getFloat32(pointer + 12, true),
        ],
        scale: memory.getFloat32(pointer + 16, true),
        flip: memory.getUint32(pointer + 20, true),
        translation: [
            memory.getFloat32(pointer + 24, true),
            memory.getFloat32(pointer + 28, true),
            memory.getFloat32(pointer + 32, true),
        ],
    };
}


function readCString(pointer, capacity) {
    const bytes = Uint8Array.from(decoder.HEAPU8.subarray(pointer, pointer + capacity));
    const terminator = bytes.indexOf(0);
    return new TextDecoder().decode(terminator < 0 ? bytes : bytes.subarray(0, terminator));
}

function findContentLayerIndex(layerId) {
    const layerPointer = decoder._malloc(LAYER_INFO_SIZE);
    try {
        const layerCount = decoder._imm_web_get_layer_count();
        for (let layerIndex = 0; layerIndex < layerCount; layerIndex++) {
            if (decoder._imm_web_get_layer_info(layerIndex, layerPointer) === 0) continue;
            const memory = new DataView(decoder.HEAPU8.buffer);
            if (memory.getUint32(layerPointer, true) === layerId) return layerIndex;
        }
        return -1;
    } finally {
        decoder._free(layerPointer);
    }
}

function marshalDrawing(layerId, drawingId) {
    const layerIndex = findContentLayerIndex(layerId);
    if (layerIndex < 0) throw new Error(`Could not find paint layer ${layerId}`);
    const strokeCount = decoder._imm_web_get_stroke_count(layerIndex, drawingId);
    const descriptors = new Uint32Array(strokeCount * 4);
    const bounds = new Float32Array(strokeCount * 6);
    const pointCounts = new Uint32Array(strokeCount);
    const strokeInfoPointer = decoder._malloc(STROKE_INFO_SIZE);
    let totalPointCount = 0;
    try {
        for (let strokeIndex = 0; strokeIndex < strokeCount; strokeIndex++) {
            if (decoder._imm_web_get_stroke_info(layerIndex, drawingId, strokeIndex, strokeInfoPointer) === 0) {
                throw new Error(`Could not read stroke ${layerId}/${drawingId}/${strokeIndex}`);
            }
            const memory = new DataView(decoder.HEAPU8.buffer);
            const pointCount = memory.getUint32(strokeInfoPointer + 8, true);
            pointCounts[strokeIndex] = pointCount;
            descriptors[strokeIndex * 4] = totalPointCount;
            descriptors[strokeIndex * 4 + 1] = pointCount;
            descriptors[strokeIndex * 4 + 2] = memory.getUint32(strokeInfoPointer, true);
            descriptors[strokeIndex * 4 + 3] = memory.getUint32(strokeInfoPointer + 4, true);
            for (let component = 0; component < 6; component++) {
                bounds[strokeIndex * 6 + component] = memory.getFloat32(
                    strokeInfoPointer + 16 + component * 4, true);
            }
            totalPointCount += pointCount;
        }
    } finally {
        decoder._free(strokeInfoPointer);
    }

    const points = new Float32Array(totalPointCount * STROKE_POINT_FLOATS);
    const pointTimes = new Float32Array(totalPointCount);
    const maximumPointCount = pointCounts.reduce((maximum, value) => Math.max(maximum, value), 0);
    const pointsPointer = maximumPointCount > 0 ? decoder._malloc(maximumPointCount * STROKE_POINT_SIZE) : 0;
    try {
        for (let strokeIndex = 0; strokeIndex < strokeCount; strokeIndex++) {
            const pointCount = pointCounts[strokeIndex];
            if (pointCount === 0) continue;
            if (decoder._imm_web_get_stroke_points(
                layerIndex, drawingId, strokeIndex, pointsPointer, pointCount) !== pointCount) {
                throw new Error(`Could not read points for stroke ${layerId}/${drawingId}/${strokeIndex}`);
            }
            points.set(
                new Float32Array(decoder.HEAPU8.buffer, pointsPointer, pointCount * STROKE_POINT_FLOATS),
                descriptors[strokeIndex * 4] * STROKE_POINT_FLOATS,
            );
            if (decoder._imm_web_get_stroke_point_times(
                layerIndex, drawingId, strokeIndex, pointsPointer, pointCount) !== pointCount) {
                throw new Error(`Could not read point times for stroke ${layerId}/${drawingId}/${strokeIndex}`);
            }
            pointTimes.set(
                new Float32Array(decoder.HEAPU8.buffer, pointsPointer, pointCount),
                descriptors[strokeIndex * 4],
            );
        }
    } finally {
        if (pointsPointer !== 0) decoder._free(pointsPointer);
    }

    const biggestStroke = decoder._imm_web_get_drawing_biggest_stroke(layerIndex, drawingId);
    const geometries = packPaintGeometry({ biggestStroke, descriptors, bounds, points, pointTimes });
    const transfers = geometries.flatMap((geometry) => [
        geometry.positions.buffer,
        geometry.colors.buffer,
        geometry.directions.buffer,
        geometry.visibility.buffer,
        geometry.masks.buffer,
        geometry.progress.buffer,
        geometry.indices.buffer,
    ]);
    return {
        delta: {
            type: "drawing",
            layerId,
            drawingId,
            drawing: { biggestStroke, strokeCount, pointCount: totalPointCount, geometries },
        },
        transfers,
    };
}

function marshalLayerAsset(layerId) {
    const transfers = [];
    let picture;
    const contentLayerIndex = findContentLayerIndex(layerId);
    if (contentLayerIndex >= 0) {
        const infoPointer = decoder._malloc(PICTURE_INFO_SIZE);
        try {
            if (decoder._imm_web_get_picture_info(contentLayerIndex, infoPointer) !== 0) {
                let memory = new DataView(decoder.HEAPU8.buffer);
                const dataSize = memory.getUint32(infoPointer + 24, true);
                const pixelsPointer = dataSize > 0 ? decoder._malloc(dataSize) : 0;
                try {
                    if (dataSize > 0 && decoder._imm_web_get_picture_pixels(
                        contentLayerIndex, pixelsPointer, dataSize) !== dataSize) {
                        throw new Error(`Could not read picture pixels for layer ${layerId}`);
                    }
                    memory = new DataView(decoder.HEAPU8.buffer);
                    const pixels = new Uint8Array(dataSize);
                    if (dataSize > 0) pixels.set(decoder.HEAPU8.subarray(pixelsPointer, pixelsPointer + dataSize));
                    picture = {
                        contentType: memory.getUint32(infoPointer + 4, true),
                        viewerLocked: memory.getUint32(infoPointer + 8, true) !== 0,
                        width: memory.getUint32(infoPointer + 12, true),
                        height: memory.getUint32(infoPointer + 16, true),
                        hasAlpha: memory.getUint32(infoPointer + 20, true) !== 0,
                        pixels,
                    };
                    transfers.push(pixels.buffer);
                } finally {
                    if (pixelsPointer !== 0) decoder._free(pixelsPointer);
                }
            }
        } finally {
            decoder._free(infoPointer);
        }
    }

    let sound;
    const playbackPointer = decoder._malloc(PLAYBACK_INFO_SIZE);
    const timelinePointer = decoder._malloc(TIMELINE_LAYER_INFO_SIZE);
    const soundPointer = decoder._malloc(SOUND_INFO_SIZE);
    try {
        if (decoder._imm_web_get_playback_info(playbackPointer) !== 0) {
            let memory = new DataView(decoder.HEAPU8.buffer);
            const timelineCount = memory.getUint32(playbackPointer + 8, true);
            for (let index = 0; index < timelineCount; index++) {
                if (decoder._imm_web_get_timeline_layer_info(index, timelinePointer) === 0) continue;
                memory = new DataView(decoder.HEAPU8.buffer);
                if (memory.getUint32(timelinePointer, true) !== layerId ||
                    decoder._imm_web_get_sound_info(index, soundPointer) === 0) continue;
                memory = new DataView(decoder.HEAPU8.buffer);
                const dataSize = memory.getUint32(soundPointer + 60, true);
                const bytesPointer = dataSize > 0 ? decoder._malloc(dataSize) : 0;
                try {
                    if (dataSize > 0 && decoder._imm_web_get_sound_bytes(index, bytesPointer, dataSize) !== dataSize) {
                        throw new Error(`Could not read sound bytes for layer ${layerId}`);
                    }
                    memory = new DataView(decoder.HEAPU8.buffer);
                    const bytes = new Uint8Array(dataSize);
                    if (dataSize > 0) bytes.set(decoder.HEAPU8.subarray(bytesPointer, bytesPointer + dataSize));
                    sound = {
                        type: memory.getUint32(soundPointer + 4, true),
                        assetFormat: memory.getUint32(soundPointer + 8, true),
                        channelCount: memory.getUint32(soundPointer + 12, true),
                        looping: memory.getUint32(soundPointer + 16, true) !== 0,
                        playOnLoad: memory.getUint32(soundPointer + 20, true) !== 0,
                        gain: memory.getFloat32(soundPointer + 24, true),
                        attenuationType: memory.getUint32(soundPointer + 28, true),
                        attenuationMin: memory.getFloat32(soundPointer + 32, true),
                        attenuationMax: memory.getFloat32(soundPointer + 36, true),
                        modifierType: memory.getUint32(soundPointer + 40, true),
                        modifierParameters: Array.from({ length: 4 }, (_, component) =>
                            memory.getFloat32(soundPointer + 44 + component * 4, true)),
                        bytes,
                    };
                    transfers.push(bytes.buffer);
                } finally {
                    if (bytesPointer !== 0) decoder._free(bytesPointer);
                }
                break;
            }
        }
    } finally {
        decoder._free(soundPointer);
        decoder._free(timelinePointer);
        decoder._free(playbackPointer);
    }
    return { delta: { type: "asset", layerId, picture, sound }, transfers };
}

function decodeStagedDelta(message) {
    const errorPointer = decoder._malloc(ERROR_SIZE);
    try {
        const status = message.type === "decodeDrawing"
            ? decoder._imm_web_decode_drawing(message.layerId, message.drawingId, errorPointer)
            : decoder._imm_web_decode_layer_asset(message.layerId, errorPointer);
        if (status !== 0) {
            return { ok: false, error: readError(new DataView(decoder.HEAPU8.buffer), errorPointer) };
        }
        const result = message.type === "decodeDrawing"
            ? marshalDrawing(message.layerId, message.drawingId)
            : marshalLayerAsset(message.layerId);
        return { ok: true, ...result };
    } finally {
        decoder._free(errorPointer);
    }
}


function decodeScene(source, operation = { type: "decode" }) {
    const requiresSource = operation.type === "decode" || operation.type === "openMetadata";
    if (requiresSource && !(source instanceof ArrayBuffer)) {
        throw new TypeError(`${operation.type} requires an ArrayBuffer`);
    }
    if (requiresSource && source.byteLength > MAX_WASM32_SOURCE_SIZE) {
        throw new RangeError("IMM source exceeds the Wasm32 address space");
    }

    const startedAt = performance.now();
    const sourceLength = requiresSource ? source.byteLength : 0;
    if (requiresSource && stagedSourcePointer !== 0) {
        decoder._imm_web_release_scene();
        decoder._free(stagedSourcePointer);
        stagedSourcePointer = 0;
    }
    const sourcePointer = sourceLength > 0 ? decoder._malloc(sourceLength) : 0;
    const errorPointer = decoder._malloc(ERROR_SIZE);
    try {
        if (sourceLength > 0) {
            decoder.HEAPU8.set(new Uint8Array(source), sourcePointer);
        }
        let status;
        if (operation.type === "openMetadata") {
            status = decoder._imm_web_open_scene_metadata(sourcePointer, sourceLength, errorPointer);
        } else if (operation.type === "decodeDrawing") {
            status = decoder._imm_web_decode_drawing(operation.layerId, operation.drawingId, errorPointer);
        } else if (operation.type === "decodeLayerAsset") {
            status = decoder._imm_web_decode_layer_asset(operation.layerId, errorPointer);
        } else if (operation.type === "fallbackEager") {
            status = decoder._imm_web_decode_open_scene_eager(errorPointer);
        } else {
            status = decoder._imm_web_decode_scene(sourcePointer, sourceLength, errorPointer);
        }
        let memory = new DataView(decoder.HEAPU8.buffer);
        if (status !== 0) {
            if (operation.type === "openMetadata") stagedSourcePointer = sourcePointer;
            return { ok: false, error: readError(memory, errorPointer) };
        }
        if (operation.type === "openMetadata") stagedSourcePointer = sourcePointer;
        const decodedAt = performance.now();
        let packMs = 0;
        const backgroundPointer = decoder._malloc(3 * Float32Array.BYTES_PER_ELEMENT);
        const layerPointer = decoder._malloc(LAYER_INFO_SIZE);
        const localPointer = decoder._malloc(TRANSFORM_SIZE);
        const worldPointer = decoder._malloc(TRANSFORM_SIZE);
        const pivotPointer = decoder._malloc(TRANSFORM_SIZE);
        const animationPointer = decoder._malloc(ANIMATION_INFO_SIZE);
        const strokeInfoPointer = decoder._malloc(STROKE_INFO_SIZE);
        const pictureInfoPointer = decoder._malloc(PICTURE_INFO_SIZE);
        const soundInfoPointer = decoder._malloc(SOUND_INFO_SIZE);
        const playbackInfoPointer = decoder._malloc(PLAYBACK_INFO_SIZE);
        const timelineLayerPointer = decoder._malloc(TIMELINE_LAYER_INFO_SIZE);
        const animationKeyPointer = decoder._malloc(ANIMATION_KEY_SIZE);
        const chapterPointer = decoder._malloc(CHAPTER_INFO_SIZE);
        const keepAlivePointer = decoder._malloc(KEEP_ALIVE_INFO_SIZE);
        try {
            decoder._imm_web_get_background_color(backgroundPointer, 3);
            memory = new DataView(decoder.HEAPU8.buffer);
            const backgroundColor = [
                memory.getFloat32(backgroundPointer, true),
                memory.getFloat32(backgroundPointer + 4, true),
                memory.getFloat32(backgroundPointer + 8, true),
            ];
            const contentLayers = [];
            const transfers = [];
            const layerCount = decoder._imm_web_get_layer_count();
            for (let layerIndex = 0; layerIndex < layerCount; layerIndex++) {
                if (decoder._imm_web_get_layer_info(layerIndex, layerPointer) === 0) {
                    throw new Error(`Could not read decoded layer ${layerIndex}`);
                }
                if (decoder._imm_web_get_layer_transforms(
                    layerIndex, localPointer, worldPointer, pivotPointer) === 0) {
                    throw new Error(`Could not read transforms for decoded layer ${layerIndex}`);
                }
                memory = new DataView(decoder.HEAPU8.buffer);
                const layer = {
                    id: memory.getUint32(layerPointer, true),
                    type: memory.getUint32(layerPointer + 4, true),
                    name: readCString(layerPointer + LAYER_NAME_OFFSET, LAYER_NAME_CAPACITY),
                    visible: memory.getUint32(layerPointer + 12, true) !== 0,
                    opacity: memory.getFloat32(layerPointer + 16, true),
                    defaultSpawn: memory.getUint32(layerPointer + 20, true) !== 0,
                    localTransform: readTransform(memory, localPointer),
                    worldTransform: readTransform(memory, worldPointer),
                    pivotTransform: readTransform(memory, pivotPointer),
                    frameRate: 0,
                    frameCount: 0,
                    maxRepeatCount: 0,
                    frameBuffer: new Uint32Array(),
                    drawings: [],
                };

                if (layer.type === 1 && decoder._imm_web_get_animation_info(layerIndex, animationPointer) !== 0) {
                    memory = new DataView(decoder.HEAPU8.buffer);
                    layer.frameRate = memory.getUint32(animationPointer, true);
                    layer.frameCount = memory.getUint32(animationPointer + 4, true);
                    layer.maxRepeatCount = memory.getUint32(animationPointer + 8, true);
                    if (layer.frameCount > 0) {
                        const framesPointer = decoder._malloc(layer.frameCount * Uint32Array.BYTES_PER_ELEMENT);
                        try {
                            const frameCount = decoder._imm_web_get_frame_buffer(
                                layerIndex, framesPointer, layer.frameCount);
                            layer.frameBuffer = new Uint32Array(frameCount);
                            layer.frameBuffer.set(new Uint32Array(
                                decoder.HEAPU8.buffer, framesPointer, frameCount));
                            transfers.push(layer.frameBuffer.buffer);
                        } finally {
                            decoder._free(framesPointer);
                        }
                    }

                    const drawingCount = decoder._imm_web_get_drawing_count(layerIndex);
                    for (let drawingIndex = 0; drawingIndex < drawingCount; drawingIndex++) {
                        const strokeCount = decoder._imm_web_get_stroke_count(layerIndex, drawingIndex);
                        const descriptors = new Uint32Array(strokeCount * 4);
                        const bounds = new Float32Array(strokeCount * 6);
                        const pointCounts = new Uint32Array(strokeCount);
                        let totalPointCount = 0;
                        for (let strokeIndex = 0; strokeIndex < strokeCount; strokeIndex++) {
                            if (decoder._imm_web_get_stroke_info(
                                layerIndex, drawingIndex, strokeIndex, strokeInfoPointer) === 0) {
                                throw new Error(`Could not read stroke ${layerIndex}/${drawingIndex}/${strokeIndex}`);
                            }
                            memory = new DataView(decoder.HEAPU8.buffer);
                            const pointCount = memory.getUint32(strokeInfoPointer + 8, true);
                            pointCounts[strokeIndex] = pointCount;
                            descriptors[strokeIndex * 4] = totalPointCount;
                            descriptors[strokeIndex * 4 + 1] = pointCount;
                            descriptors[strokeIndex * 4 + 2] = memory.getUint32(strokeInfoPointer, true);
                            descriptors[strokeIndex * 4 + 3] = memory.getUint32(strokeInfoPointer + 4, true);
                            for (let component = 0; component < 6; component++) {
                                bounds[strokeIndex * 6 + component] = memory.getFloat32(
                                    strokeInfoPointer + 16 + component * 4, true);
                            }
                            totalPointCount += pointCount;
                        }

                        const points = new Float32Array(totalPointCount * STROKE_POINT_FLOATS);
                        const pointTimes = new Float32Array(totalPointCount);
                        const maximumPointCount = pointCounts.reduce((maximum, value) => Math.max(maximum, value), 0);
                        const pointsPointer = maximumPointCount > 0
                            ? decoder._malloc(maximumPointCount * STROKE_POINT_SIZE)
                            : 0;
                        try {
                            for (let strokeIndex = 0; strokeIndex < strokeCount; strokeIndex++) {
                                const pointCount = pointCounts[strokeIndex];
                                if (pointCount === 0) continue;
                                const copied = decoder._imm_web_get_stroke_points(
                                    layerIndex, drawingIndex, strokeIndex, pointsPointer, pointCount);
                                if (copied !== pointCount) {
                                    throw new Error(`Could not read points for stroke ${layerIndex}/${drawingIndex}/${strokeIndex}`);
                                }
                                points.set(
                                    new Float32Array(decoder.HEAPU8.buffer, pointsPointer, copied * STROKE_POINT_FLOATS),
                                    descriptors[strokeIndex * 4] * STROKE_POINT_FLOATS,
                                );
                                const copiedTimes = decoder._imm_web_get_stroke_point_times(
                                    layerIndex, drawingIndex, strokeIndex, pointsPointer, pointCount);
                                if (copiedTimes !== pointCount) {
                                    throw new Error(`Could not read point times for stroke ${layerIndex}/${drawingIndex}/${strokeIndex}`);
                                }
                                pointTimes.set(
                                    new Float32Array(decoder.HEAPU8.buffer, pointsPointer, copiedTimes),
                                    descriptors[strokeIndex * 4],
                                );
                            }
                        } finally {
                            if (pointsPointer !== 0) decoder._free(pointsPointer);
                        }
                        const drawingSource = {
                            biggestStroke: decoder._imm_web_get_drawing_biggest_stroke(layerIndex, drawingIndex),
                            descriptors,
                            bounds,
                            points,
                            pointTimes,
                        };
                        const packStartedAt = performance.now();
                        const geometries = packPaintGeometry(drawingSource);
                        packMs += performance.now() - packStartedAt;
                        layer.drawings.push({
                            biggestStroke: drawingSource.biggestStroke,
                            strokeCount,
                            pointCount: totalPointCount,
                            geometries,
                        });
                        for (const geometry of geometries) {
                            transfers.push(
                                geometry.positions.buffer,
                                geometry.colors.buffer,
                                geometry.directions.buffer,
                                geometry.visibility.buffer,
                                geometry.masks.buffer,
                                geometry.progress.buffer,
                                geometry.indices.buffer,
                            );
                        }
                    }
                } else if (layer.type === 4 && decoder._imm_web_get_picture_info(layerIndex, pictureInfoPointer) !== 0) {
                    memory = new DataView(decoder.HEAPU8.buffer);
                    const dataSize = memory.getUint32(pictureInfoPointer + 24, true);
                    const pixelsPointer = decoder._malloc(dataSize);
                    try {
                        const copied = decoder._imm_web_get_picture_pixels(layerIndex, pixelsPointer, dataSize);
                        if (copied !== dataSize) {
                            throw new Error(`Could not read picture pixels for layer ${layerIndex}`);
                        }
                        const pixels = new Uint8Array(dataSize);
                        pixels.set(decoder.HEAPU8.subarray(pixelsPointer, pixelsPointer + dataSize));
                        layer.picture = {
                            contentType: memory.getUint32(pictureInfoPointer + 4, true),
                            viewerLocked: memory.getUint32(pictureInfoPointer + 8, true) !== 0,
                            width: memory.getUint32(pictureInfoPointer + 12, true),
                            height: memory.getUint32(pictureInfoPointer + 16, true),
                            hasAlpha: memory.getUint32(pictureInfoPointer + 20, true) !== 0,
                            pixels,
                        };
                        transfers.push(pixels.buffer);
                    } finally {
                        decoder._free(pixelsPointer);
                    }
                }
                contentLayers.push(layer);
            }

            if (decoder._imm_web_get_playback_info(playbackInfoPointer) === 0) {
                throw new Error("Could not read decoded playback metadata");
            }
            memory = new DataView(decoder.HEAPU8.buffer);
            const ticksPerSecond = memory.getUint32(playbackInfoPointer, true);
            const animateOnStart = memory.getUint32(playbackInfoPointer + 4, true) !== 0;
            const timelineLayerCount = memory.getUint32(playbackInfoPointer + 8, true);
            const chapterCount = memory.getUint32(playbackInfoPointer + 12, true);
            const durationTicks = Number(memory.getBigInt64(playbackInfoPointer + 16, true));
            const layers = [];
            const claimedContentLayers = new Set();
            for (let layerIndex = 0; layerIndex < timelineLayerCount; layerIndex++) {
                if (decoder._imm_web_get_timeline_layer_info(layerIndex, timelineLayerPointer) === 0) {
                    throw new Error(`Could not read timeline layer ${layerIndex}`);
                }
                if (decoder._imm_web_get_timeline_layer_transforms(
                    layerIndex, localPointer, worldPointer, pivotPointer) === 0) {
                    throw new Error(`Could not read timeline transforms ${layerIndex}`);
                }
                memory = new DataView(decoder.HEAPU8.buffer);
                const flags = memory.getUint32(timelineLayerPointer + 12, true);
                const layerType = memory.getUint32(timelineLayerPointer + 8, true);
                const contentLayerIndex = memory.getUint32(timelineLayerPointer + 36, true);
                const keyCount = memory.getUint32(timelineLayerPointer + 32, true);
                const content = contentLayerIndex < contentLayers.length
                    ? contentLayers[contentLayerIndex]
                    : undefined;
                if (content !== undefined) claimedContentLayers.add(contentLayerIndex);
                const keys = [];
                for (let keyIndex = 0; keyIndex < keyCount; keyIndex++) {
                    if (decoder._imm_web_get_animation_key(layerIndex, keyIndex, animationKeyPointer) === 0) {
                        throw new Error(`Could not read animation key ${layerIndex}/${keyIndex}`);
                    }
                    memory = new DataView(decoder.HEAPU8.buffer);
                    keys.push({
                        property: memory.getUint32(animationKeyPointer, true),
                        interpolation: memory.getUint32(animationKeyPointer + 4, true),
                        timeTicks: Number(memory.getBigInt64(animationKeyPointer + 8, true)),
                        boolValue: memory.getUint32(animationKeyPointer + 16, true) !== 0,
                        uintValue: memory.getUint32(animationKeyPointer + 20, true),
                        floatValue: memory.getFloat32(animationKeyPointer + 24, true),
                        doubleValue: memory.getFloat64(animationKeyPointer + 32, true),
                        transformValue: readTransform(memory, animationKeyPointer + 40),
                    });
                }
                memory = new DataView(decoder.HEAPU8.buffer);
                if (decoder._imm_web_get_keep_alive_info(layerIndex, keepAlivePointer) === 0) {
                    throw new Error(`Could not read keep-alive metadata ${layerIndex}`);
                }
                memory = new DataView(decoder.HEAPU8.buffer);
                const keepAlive = {
                    type: memory.getUint32(keepAlivePointer, true),
                    waveform: memory.getUint32(keepAlivePointer + 4, true),
                    parameters: Array.from({ length: 6 }, (_, index) =>
                        memory.getFloat32(keepAlivePointer + 8 + index * 4, true)),
                };
                let sound;
                if (layerType === 5 && decoder._imm_web_get_sound_info(layerIndex, soundInfoPointer) !== 0) {
                    memory = new DataView(decoder.HEAPU8.buffer);
                    const dataSize = memory.getUint32(soundInfoPointer + 60, true);
                    const bytesPointer = dataSize > 0 ? decoder._malloc(dataSize) : 0;
                    try {
                        memory = new DataView(decoder.HEAPU8.buffer);
                        if (dataSize > 0 && decoder._imm_web_get_sound_bytes(
                            layerIndex, bytesPointer, dataSize) !== dataSize) {
                            throw new Error(`Could not read sound bytes ${layerIndex}`);
                        }
                        const bytes = new Uint8Array(dataSize);
                        if (dataSize > 0) bytes.set(decoder.HEAPU8.subarray(bytesPointer, bytesPointer + dataSize));
                        sound = {
                            type: memory.getUint32(soundInfoPointer + 4, true),
                            assetFormat: memory.getUint32(soundInfoPointer + 8, true),
                            channelCount: memory.getUint32(soundInfoPointer + 12, true),
                            looping: memory.getUint32(soundInfoPointer + 16, true) !== 0,
                            playOnLoad: memory.getUint32(soundInfoPointer + 20, true) !== 0,
                            gain: memory.getFloat32(soundInfoPointer + 24, true),
                            attenuationType: memory.getUint32(soundInfoPointer + 28, true),
                            attenuationMin: memory.getFloat32(soundInfoPointer + 32, true),
                            attenuationMax: memory.getFloat32(soundInfoPointer + 36, true),
                            modifierType: memory.getUint32(soundInfoPointer + 40, true),
                            modifierParameters: Array.from({ length: 4 }, (_, index) =>
                                memory.getFloat32(soundInfoPointer + 44 + index * 4, true)),
                            bytes,
                        };
                        transfers.push(bytes.buffer);
                    } finally {
                        if (bytesPointer !== 0) decoder._free(bytesPointer);
                    }
                    memory = new DataView(decoder.HEAPU8.buffer);
                }
                layers.push({
                    ...(content ?? {
                        defaultSpawn: false,
                        frameRate: 0,
                        frameCount: 0,
                        frameBuffer: new Uint32Array(),
                        drawings: [],
                    }),
                    id: memory.getUint32(timelineLayerPointer, true),
                    parentId: memory.getInt32(timelineLayerPointer + 4, true),
                    type: layerType,
                    name: readCString(
                        timelineLayerPointer + TIMELINE_LAYER_NAME_OFFSET,
                        LAYER_NAME_CAPACITY,
                    ),
                    visible: (flags & 1) !== 0,
                    isTimeline: (flags & 2) !== 0,
                    spawnTracking: layerType === 8 ? ((flags & 4) !== 0 ? "floor" : "eye") : null,
                    opacity: memory.getFloat32(timelineLayerPointer + 16, true),
                    maxRepeatCount: memory.getUint32(timelineLayerPointer + 20, true),
                    durationTicks: Number(memory.getBigInt64(timelineLayerPointer + 24, true)),
                    localTransform: readTransform(memory, localPointer),
                    worldTransform: readTransform(memory, worldPointer),
                    pivotTransform: readTransform(memory, pivotPointer),
                    keys,
                    keepAlive,
                    sound,
                });
            }
            for (let contentIndex = 0; contentIndex < contentLayers.length; contentIndex++) {
                if (!claimedContentLayers.has(contentIndex)) {
                    layers.push({
                        ...contentLayers[contentIndex],
                        parentId: -1,
                        isTimeline: false,
                        durationTicks: 0,
                        keys: [],
                    });
                }
            }
            const chapters = [];
            for (let chapterIndex = 0; chapterIndex < chapterCount; chapterIndex++) {
                if (decoder._imm_web_get_chapter_info(chapterIndex, chapterPointer) === 0) {
                    throw new Error(`Could not read chapter ${chapterIndex}`);
                }
                memory = new DataView(decoder.HEAPU8.buffer);
                chapters.push({
                    startTicks: Number(memory.getBigInt64(chapterPointer, true)),
                    endTicks: Number(memory.getBigInt64(chapterPointer + 8, true)),
                    markerAction: memory.getUint32(chapterPointer + 16, true),
                });
            }
            const marshalledAt = performance.now();
            return {
                ok: true,
                document: {
                    schemaVersion: decoder._imm_web_schema_version(),
                    backgroundColor,
                    ticksPerSecond,
                    animateOnStart,
                    durationTicks,
                    chapters,
                    layers,
                    metrics: {
                        decodeMs: decodedAt - startedAt,
                        marshalMs: marshalledAt - decodedAt - packMs,
                        packMs,
                    },
                },
                transfers,
            };
        } finally {
            decoder._free(keepAlivePointer);
            decoder._free(chapterPointer);
            decoder._free(animationKeyPointer);
            decoder._free(timelineLayerPointer);
            decoder._free(playbackInfoPointer);
            decoder._free(soundInfoPointer);
            decoder._free(pictureInfoPointer);
            decoder._free(strokeInfoPointer);
            decoder._free(animationPointer);
            decoder._free(pivotPointer);
            decoder._free(worldPointer);
            decoder._free(localPointer);
            decoder._free(layerPointer);
            decoder._free(backgroundPointer);
            if (operation.type === "decode" || operation.type === "fallbackEager") {
                decoder._imm_web_release_scene();
                if (operation.type === "fallbackEager" && stagedSourcePointer !== 0) {
                    decoder._free(stagedSourcePointer);
                    stagedSourcePointer = 0;
                }
            }
        }
    } finally {
        decoder._free(errorPointer);
        if (sourcePointer !== 0 && sourcePointer !== stagedSourcePointer) decoder._free(sourcePointer);
    }
}


async function handleMessage(message, send) {
    const { requestId, type, source } = message;
    const requestTypes = new Set([
        "inspect",
        "decode",
        "openMetadata",
        "decodeDrawing",
        "decodeLayerAsset",
        "fallbackEager",
        "release",
    ]);
    if (!requestTypes.has(type)) {
        send({
            requestId,
            ok: false,
            error: { status: 1, byteOffset: 0n, message: `Unknown decoder request type: ${type}` },
        });
        return;
    }

    try {
        await decoderReady;
        if (type === "inspect") {
            send({ requestId, ...inspect(source) });
        } else if (type === "release") {
            decoder._imm_web_release_scene();
            if (stagedSourcePointer !== 0) {
                decoder._free(stagedSourcePointer);
                stagedSourcePointer = 0;
            }
            send({ requestId, ok: true });
        } else if (type === "decodeDrawing" || type === "decodeLayerAsset") {
            const result = decodeStagedDelta(message);
            const transfers = result.transfers ?? [];
            delete result.transfers;
            send({ requestId, ...result }, transfers);
        } else {
            const result = decodeScene(source, {
                type,
                layerId: message.layerId,
                drawingId: message.drawingId,
            });
            const transfers = result.transfers ?? [];
            delete result.transfers;
            send({ requestId, ...result }, transfers);
        }
    } catch (error) {
        send({
            requestId,
            ok: false,
            error: {
                status: 1,
                byteOffset: 0n,
                message: error instanceof Error ? error.message : String(error),
            },
        });
    }
}


if (typeof self !== "undefined" && typeof self.postMessage === "function") {
    self.onmessage = (event) => handleMessage(
        event.data,
        (value, transfers = []) => self.postMessage(value, transfers),
    );
} else {
    const { parentPort } = await import("node:worker_threads");
    if (parentPort === null) {
        throw new Error("IMM decoder worker requires a worker message port");
    }
    parentPort.on("message", (value) => handleMessage(
        value,
        (response, transfers = []) => parentPort.postMessage(response, transfers),
    ));
}
