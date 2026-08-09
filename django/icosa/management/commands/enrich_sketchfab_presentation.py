import math
import json
from string import Template
from typing import Dict, Optional, Iterable, List

from django.core.management.base import BaseCommand, CommandError

from icosa.models import Asset


def _quat_from_lookat(position, target, up):
    try:
        px, py, pz = position
        tx, ty, tz = target
        ux, uy, uz = up
        fx, fy, fz = tx - px, ty - py, tz - pz
        fl = math.sqrt(fx * fx + fy * fy + fz * fz) or 1.0
        fx, fy, fz = fx / fl, fy / fl, fz / fl
        rx, ry, rz = (fy * uz - fz * uy, fz * ux - fx * uz, fx * uy - fy * ux)
        rl = math.sqrt(rx * rx + ry * ry + rz * rz) or 1.0
        rx, ry, rz = rx / rl, ry / rl, rz / rl
        ux2, uy2, uz2 = (ry * fz - rz * fy, rz * fx - rx * fz, rx * fy - ry * fx)
        m00, m01, m02 = rx, ux2, -fx
        m10, m11, m12 = ry, uy2, -fy
        m20, m21, m22 = rz, uz2, -fz
        trace = m00 + m11 + m22
        if trace > 0:
            s = math.sqrt(trace + 1.0) * 2.0
            w = 0.25 * s
            x = (m21 - m12) / s
            y = (m02 - m20) / s
            z = (m10 - m01) / s
        elif (m00 > m11) and (m00 > m22):
            s = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
            w = (m21 - m12) / s
            x = 0.25 * s
            y = (m01 + m10) / s
            z = (m02 + m20) / s
        elif m11 > m22:
            s = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
            w = (m02 - m20) / s
            x = (m01 + m10) / s
            y = 0.25 * s
            z = (m12 + m21) / s
        else:
            s = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
            w = (m10 - m01) / s
            x = (m02 + m20) / s
            y = (m12 + m21) / s
            z = 0.25 * s
        return [x, y, z, w]
    except Exception:
        return [0, 0, 0, 1]


def map_viewer_snapshot_to_presentation(snapshot: Dict) -> Optional[Dict]:
    if not snapshot:
        return None
    camera = snapshot.get("cameraLookAt") or {}
    position = camera.get("position")
    target = camera.get("target")
    up = camera.get("up") or [0, 1, 0]
    fov_deg = snapshot.get("fov")
    bg = snapshot.get("background") or {}
    env = snapshot.get("currentEnvironment")

    pres: Dict = {"camera": {"type": "perspective", "perspective": {"znear": 0.1}}}

    if position:
        pres["camera"]["translation"] = position
    if position and target:
        pres["camera"]["rotation"] = _quat_from_lookat(position, target, up)
        pres["camera"].setdefault("GOOGLE_camera_settings", {})["pivot"] = target
    pres["camera"].setdefault("GOOGLE_camera_settings", {})["mode"] = "movableOrbit"
    if isinstance(fov_deg, (int, float)):
        pres["camera"].setdefault("perspective", {})["yfov"] = math.radians(fov_deg)
    if isinstance(bg.get("color"), list) and len(bg.get("color")) >= 3:
        r, g, b = bg["color"][:3]
        def clamp01(x):
            try:
                return max(0, min(1, float(x)))
            except Exception:
                return 0
        r8 = int(round(clamp01(r) * 255))
        g8 = int(round(clamp01(g) * 255))
        b8 = int(round(clamp01(b) * 255))
        pres["backgroundColor"] = f"#{r8:02x}{g8:02x}{b8:02x}"
        pres["GOOGLE_backgrounds"] = {"color": [r, g, b]}
    if env:
        pres["GOOGLE_lighting_rig"] = env
        pres["GOOGLE_lights_image_based"] = env
    pres["orientingRotation"] = {"w": 1}
    pres["GOOGLE_scene_rotation"] = {"rotation": [0, 0, 0, 1]}
    pres["GOOGLE_real_world_transform"] = {"scaling_factor": 1}
    return pres


def fetch_sketchfab_viewer_snapshot(uid: str, timeout_ms: int = 20000) -> Optional[Dict]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise CommandError("Playwright is not installed in this environment.") from exc

    viewer_js = "https://static.sketchfab.com/api/sketchfab-viewer-1.12.1.js"
    html_template = Template(
        """
<!doctype html><html><head><meta charset=\"utf-8\"><script src=\"$viewer_js\"></script></head>
<body style=\"margin:0\"><iframe id=\"api-frame\" allow=\"autoplay; fullscreen; vr\" style=\"width:10px;height:10px;border:0\"></iframe>
<script>
const iframe=document.getElementById('api-frame');
const client=new window.Sketchfab(iframe);
function call(api, name){return new Promise((resolve)=>{if(typeof api[name]!== 'function'){return resolve(undefined);}try{api[name]((v)=>resolve(v));}catch(e){resolve(undefined);}})}
client.init('$uid', {autostart:1,ui_controls:0,ui_stop:0,success: function(api){api.addEventListener('viewerready', async function(){
  const cameraLookAt=await call(api,'getCameraLookAt');
  const fov=await call(api,'getFov');
  const background=await call(api,'getBackground');
  const currentEnvironment=await call(api,'getCurrentEnvironment');
  const postProcessing=await call(api,'getPostProcessing');
  const shading=await call(api,'getShading');
  const viewerSettings=await call(api,'getViewerSettings');
  window._snapshot={cameraLookAt,fov,background,currentEnvironment,postProcessing,shading,viewerSettings};
  console.log('SNAPSHOT:'+JSON.stringify(window._snapshot));
});},error:function(){console.error('init error')}});
</script></body></html>
"""
    )
    html = html_template.substitute(uid=uid, viewer_js=viewer_js)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_default_timeout(timeout_ms)
        snapshot = {}

        def on_console(msg):
            text = msg.text if isinstance(msg.text, str) else msg.text()
            if isinstance(text, str) and text.startswith("SNAPSHOT:"):
                try:
                    snapshot.update(json.loads(text[len("SNAPSHOT:"):]))
                except Exception:
                    pass

        page.on("console", on_console)
        from tempfile import NamedTemporaryFile
        import os
        with NamedTemporaryFile("w", delete=False, suffix=".html", encoding="utf-8") as f:
            f.write(html)
            html_path = f.name
        page.goto("file://" + os.path.abspath(html_path))
        page.wait_for_timeout(12000)
        browser.close()
        return snapshot or None


class Command(BaseCommand):
    help = "Enrich assets imported from Sketchfab with viewer presentation parameters (camera, background, environment, post-fx)."

    def add_arguments(self, parser):
        parser.add_argument("--asset", dest="assets", nargs="*", help="Asset.url values to process")
        parser.add_argument("--uid", dest="uids", nargs="*", help="Sketchfab model UIDs to process")
        parser.add_argument("--all", action="store_true", help="Process all assets imported from Sketchfab")
        parser.add_argument("--limit", type=int, default=None, help="Limit number of assets to process")
        parser.add_argument("--dry-run", action="store_true", help="Do not save; just print")

    def handle(self, *args, **opts):
        assets_arg = opts.get("assets") or []
        uids_arg = opts.get("uids") or []
        do_all = opts.get("all")
        limit = opts.get("limit")
        dry_run = opts.get("dry_run")

        targets: List[Asset] = []
        if assets_arg:
            for aurl in assets_arg:
                asset = Asset.objects.filter(url=aurl).first()
                if asset:
                    targets.append(asset)
                else:
                    self.stderr.write(f"No asset with url={aurl}")
        if uids_arg:
            for uid in uids_arg:
                a = Asset.objects.filter(polydata__uid=uid).first()
                if a:
                    targets.append(a)
                else:
                    # Try by url convention
                    a = Asset.objects.filter(url=f"sketchfab-{uid}").first()
                    if a:
                        targets.append(a)
                    else:
                        self.stderr.write(f"No asset found for uid={uid}")
        if do_all or (not targets and not uids_arg and not assets_arg):
            qs = Asset.objects.filter(imported_from="sketchfab").order_by("-create_time")
            if limit:
                qs = qs[:limit]
            targets.extend(list(qs))

        if limit and len(targets) > limit:
            targets = targets[:limit]

        if not targets:
            self.stdout.write("Nothing to process")
            return

        processed = 0
        for asset in targets:
            uid = None
            if asset.polydata and isinstance(asset.polydata, dict):
                uid = asset.polydata.get("uid")
            if not uid and asset.url and asset.url.startswith("sketchfab-"):
                uid = asset.url[len("sketchfab-") :]
            if not uid:
                self.stderr.write(f"Skipping {asset.url}: no Sketchfab uid found")
                continue

            self.stdout.write(f"Probing viewer for {asset.url} (uid={uid})...")
            snapshot = fetch_sketchfab_viewer_snapshot(uid)
            if not snapshot:
                self.stderr.write(f"  → No snapshot captured")
                continue
            pres = map_viewer_snapshot_to_presentation(snapshot)
            if not pres:
                self.stderr.write(f"  → No mappable presentation data")
                continue
            if dry_run:
                self.stdout.write(json.dumps(pres))
            else:
                asset.presentation_params = pres
                asset.save(update_fields=["presentation_params"])
                self.stdout.write("  → Saved presentation_params")
            processed += 1

        self.stdout.write(self.style.SUCCESS(f"Done. Processed {processed} assets."))

