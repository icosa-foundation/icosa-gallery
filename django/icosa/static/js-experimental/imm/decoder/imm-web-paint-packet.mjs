export const PAINT_PACKET_SCHEMA_VERSION = 1;
export const PAINT_PACKET_HEADER_SIZE = 64;
export const PAINT_PACKET_RECORD_SIZE = 48;

export function parsePaintPacket(packet, expectedLayerId, expectedDrawingId) {
    if (!(packet instanceof Uint8Array) || packet.byteOffset !== 0 || packet.byteLength < PAINT_PACKET_HEADER_SIZE) {
        throw new Error("Paint packet must be a standalone Uint8Array containing a complete header");
    }
    const memory = new DataView(packet.buffer);
    const schemaVersion = memory.getUint32(0, true);
    const byteSize = memory.getUint32(4, true);
    const resourceId = memory.getBigUint64(8, true);
    const generation = memory.getUint32(16, true);
    const layerId = memory.getUint32(20, true);
    const drawingId = memory.getUint32(24, true);
    const strokeCount = memory.getUint32(28, true);
    const pointCount = memory.getUint32(32, true);
    const geometryCount = memory.getUint32(36, true);
    const biggestStroke = memory.getFloat32(40, true);
    const recordsOffset = memory.getUint32(44, true);
    if (schemaVersion !== PAINT_PACKET_SCHEMA_VERSION) {
        throw new Error(`Paint packet schema ${schemaVersion} is unsupported; expected ${PAINT_PACKET_SCHEMA_VERSION}`);
    }
    const expectedResourceId = (BigInt(expectedLayerId) << 32n) | BigInt(expectedDrawingId);
    if (byteSize !== packet.byteLength || layerId !== expectedLayerId || drawingId !== expectedDrawingId ||
        resourceId !== expectedResourceId || generation === 0 || geometryCount > 5 ||
        recordsOffset < PAINT_PACKET_HEADER_SIZE || recordsOffset % 4 !== 0 ||
        recordsOffset + geometryCount * PAINT_PACKET_RECORD_SIZE > byteSize) {
        throw new Error(`Malformed paint packet header for ${expectedLayerId}/${expectedDrawingId}`);
    }

    const geometries = [];
    const seenBrushes = new Set();
    for (let geometryIndex = 0; geometryIndex < geometryCount; geometryIndex++) {
        const record = recordsOffset + geometryIndex * PAINT_PACKET_RECORD_SIZE;
        const brushType = memory.getUint32(record, true);
        const vertexCount = memory.getUint32(record + 4, true);
        const triangleCount = memory.getUint32(record + 8, true);
        const indexComponentBytes = memory.getUint32(record + 12, true);
        const positionsOffset = memory.getUint32(record + 16, true);
        const colorsOffset = memory.getUint32(record + 20, true);
        const directionsOffset = memory.getUint32(record + 24, true);
        const visibilityOffset = memory.getUint32(record + 28, true);
        const masksOffset = memory.getUint32(record + 32, true);
        const progressOffset = memory.getUint32(record + 36, true);
        const indicesOffset = memory.getUint32(record + 40, true);
        const indexCount = memory.getUint32(record + 44, true);
        if (brushType > 4 || seenBrushes.has(brushType) || vertexCount === 0 ||
            (indexComponentBytes !== 2 && indexComponentBytes !== 4) || indexCount !== triangleCount * 3) {
            throw new Error(`Malformed paint geometry record ${geometryIndex} for ${expectedLayerId}/${expectedDrawingId}`);
        }
        seenBrushes.add(brushType);
        assertPacketRange(positionsOffset, vertexCount * 3 * Float32Array.BYTES_PER_ELEMENT, byteSize, 4);
        assertPacketRange(colorsOffset, vertexCount * 4 * Float32Array.BYTES_PER_ELEMENT, byteSize, 4);
        assertPacketRange(directionsOffset, vertexCount * 3 * Float32Array.BYTES_PER_ELEMENT, byteSize, 4);
        assertPacketRange(visibilityOffset, vertexCount, byteSize, 1);
        assertPacketRange(masksOffset, vertexCount, byteSize, 1);
        assertPacketRange(progressOffset, vertexCount * Float32Array.BYTES_PER_ELEMENT, byteSize, 4);
        assertPacketRange(indicesOffset, indexCount * indexComponentBytes, byteSize, indexComponentBytes);

        const IndexArray = indexComponentBytes === 2 ? Uint16Array : Uint32Array;
        const indices = new IndexArray(packet.buffer, indicesOffset, indexCount);
        for (const index of indices) {
            if (index >= vertexCount) {
                throw new Error(`Paint packet index ${index} exceeds ${vertexCount} vertices`);
            }
        }
        geometries.push({
            brushType,
            triangleCount,
            positions: new Float32Array(packet.buffer, positionsOffset, vertexCount * 3),
            colors: new Float32Array(packet.buffer, colorsOffset, vertexCount * 4),
            directions: new Float32Array(packet.buffer, directionsOffset, vertexCount * 3),
            visibility: new Uint8Array(packet.buffer, visibilityOffset, vertexCount),
            masks: new Uint8Array(packet.buffer, masksOffset, vertexCount),
            progress: new Float32Array(packet.buffer, progressOffset, vertexCount),
            indices,
        });
    }
    return {
        drawing: { biggestStroke, strokeCount, pointCount, geometries },
        resourceId,
        generation,
    };
}

function assertPacketRange(offset, byteLength, packetByteSize, alignment) {
    if (!Number.isSafeInteger(offset) || !Number.isSafeInteger(byteLength) ||
        offset < PAINT_PACKET_HEADER_SIZE || offset % alignment !== 0 || byteLength < 0 ||
        offset + byteLength > packetByteSize) {
        throw new Error(`Paint packet range ${offset}+${byteLength} exceeds ${packetByteSize} bytes or is misaligned`);
    }
}
