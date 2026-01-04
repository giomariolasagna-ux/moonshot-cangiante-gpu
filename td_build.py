# TD build: File In TOP (static image) + GLSL, shader written into glsl1_pixel
# Run:
# exec(open("C:/Users/Administrator/moonshot-td-gpu/td_build.py", encoding="utf-8-sig").read())

import json, os

CFG_PATH = r"C:/Users/Administrator/moonshot-td-gpu/config.json"

def safe_destroy(path):
    o = op(path)
    if o:
        try: o.destroy()
        except: pass

def _shader_src(warp):
    return f"""
#include <TD/TDCommon.glsl>
uniform sampler2D sTD2DInputs[1];
out vec4 fragColor;

void main()
{{
    float warp = {warp:.5f};
    vec2 uv = TDFragCoordToUV(gl_FragCoord.xy);
    vec2 c = uv - 0.5;
    float r = length(c);
    uv += c * warp * r;
    fragColor = texture(sTD2DInputs[0], uv);
}}
"""

def set_warp(val):
    op("/project1/glsl1_pixel").text = _shader_src(val)
    print("warp =", val)

def build():
    root = op("/project1")

    for name in ["filein1","glsl1","out1"]:
        safe_destroy("/project1/" + name)

    with open(CFG_PATH, "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)

    img_path = cfg["image_path"].replace("\\","/")
    print("Using image_path:", img_path)
    print("Exists on disk:", os.path.exists(img_path))

    fin = root.create("fileinTOP", "filein1")
    fin.par.file = img_path
    # force load
    try:
        fin.par.reloadpulse.pulse()
    except:
        pass

    glsl = root.create("glslTOP", "glsl1")
    glsl.inputConnectors[0].connect(fin)

    out1 = root.create("outTOP", "out1")
    out1.inputConnectors[0].connect(glsl)
    out1.openViewer()

    pix = op("/project1/glsl1_pixel")
    if not pix:
        raise Exception("glsl1_pixel not found.")
    pix.text = _shader_src(0.0)

    print("TD BUILD OK. Use set_warp(x).")
    print("Input errors:", fin.errors())
    print("Input warnings:", fin.warnings())

build()