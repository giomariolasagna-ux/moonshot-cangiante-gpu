import json, os

CFG_PATH = r"C:/Users/Administrator/moonshot-td-gpu/config.json"
SHADER_PATH = r"C:/Users/Administrator/moonshot-td-gpu/shader.frag"

def safe_destroy(path):
    o = op(path)
    if o:
        try: o.destroy()
        except: pass

def build():
    root = op("/project1")
    for name in ["filein1", "glsl1", "feedback1", "level1", "comp1", "out1", "udp_in", "udp_callback"]:
        safe_destroy("/project1/" + name)

    with open(CFG_PATH, "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)

    img_path = cfg["image_path"].replace("\\", "/")
    
    # HARD RESET: Caricamento forzato della texture GPU
    fin = root.create("moviefileinTOP", "filein1")
    fin.par.file = "" # Svuota buffer precedente
    fin.par.file = img_path
    fin.par.reloadpulse.pulse()

    glsl = root.create("glslTOP", "glsl1")
    glsl.inputConnectors[0].connect(fin)
    
    pix = op("/project1/glsl1_pixel") or root.create("textDAT", "glsl1_pixel")
    with open(SHADER_PATH, "r", encoding="utf-8") as f:
        pix.text = f.read()
    glsl.par.pixeldat = pix
    
    # Uniforms: uBreak in value5x
    unames = ["uWarp", "uChroma", "uGrain", "uGravity", "uPersistence", "uBreak"]
    uvals = [0.0, 0.0, 0.0, 0.5, 0.85, 0.0]
    for i, (n, v) in enumerate(zip(unames, uvals)):
        setattr(glsl.par, f"uniname{i}", n); setattr(glsl.par, f"value{i}x", v)

    # Temporal Memory Loop
    comp = root.create("compositeTOP", "comp1"); comp.par.operand = "over"; comp.inputConnectors[0].connect(glsl)
    feed = root.create("feedbackTOP", "feedback1"); feed.inputConnectors[0].connect(comp); feed.par.top = comp 
    lev = root.create("levelTOP", "level1"); lev.inputConnectors[0].connect(feed)
    lev.par.opacity.expr = "op('glsl1').par.value4x" 
    comp.inputConnectors[1].connect(lev)

    udp = root.create("udpinDAT", "udp_in"); udp.par.port = cfg.get("td_port", 5005)
    cb = root.create("textDAT", "udp_callback")
    cb.text = "import json\ndef onReceive(dat, rowIndex, message, bytes, address):\n\ttry:\n\t\td = json.loads(message)\n\t\tt = op('glsl1')\n\t\tm = {'warp':'uWarp','chroma':'uChroma','grain':'uGrain','gravity':'uGravity','energy':'uPersistence','break':'uBreak'}\n\t\tfor k, v in m.items():\n\t\t\tif k in d:\n\t\t\t\tfor i in range(10):\n\t\t\t\t\tif getattr(t.par, f'uniname{i}') == v: setattr(t.par, f'value{i}x', float(d[k])); break\n\texcept: pass"
    udp.par.callbacks = cb

    out1 = root.create("outTOP", "out1"); out1.inputConnectors[0].connect(comp); out1.openViewer()
    print(f"BUILD OK. Se vedi checkerboard, clicca 'Reload' su filein1. Asset caricato: {img_path}")

if __name__ == "__main__": build()
