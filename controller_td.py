import json, time, threading
from queue import Queue, Empty
from typing import Dict, Any, Optional

from moonshot_client import MoonshotClient
from td_sender import TDSenderUDP
from head_tracker_mp import HeadTrackerMP, ViewerState

def load_json(path: str) -> Dict[str, Any]:
    with open(path, 'r', encoding='utf-8-sig') as f:
        return json.load(f)

def load_text(path: str) -> str:
    with open(path, 'r', encoding='utf-8-sig') as f:
        return f.read()

def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))

def exp_smooth(current: float, target: float, dt: float, tau: float) -> float:
    tau = max(0.02, float(tau))
    a = 1.0 - pow(2.718281828, -dt / tau)
    return float(current + (target - current) * a)

class DecisionWorker(threading.Thread):
    def __init__(self, client: MoonshotClient, system_prompt: str):
        super().__init__(daemon=True)
        self.client = client
        self.system_prompt = system_prompt
        self.in_q = Queue(maxsize=1)
        self.out_q = Queue(maxsize=1)
        self._stop = False

    def submit(self, user_content: str):
        try:
            while True:
                self.in_q.get_nowait()
        except Empty:
            pass
        try:
            self.in_q.put_nowait(user_content)
        except Exception:
            pass

    def get_latest(self) -> Optional[Dict[str, Any]]:
        try:
            return self.out_q.get_nowait()
        except Empty:
            return None

    def run(self):
        while not self._stop:
            try:
                user_content = self.in_q.get(timeout=0.2)
            except Empty:
                continue
            try:
                d = self.client.chat_json(self.system_prompt, user_content, timeout_s=20.0)
                d = validate_decision(d)
                try:
                    while True:
                        self.out_q.get_nowait()
                except Empty:
                    pass
                self.out_q.put_nowait(d)
            except Exception:
                pass

    def stop(self):
        self._stop = True

def validate_decision(d: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(d, dict):
        return {
            \"dominant_actions\": [],
            \"support_actions\": [],
            \"energy\": 0.2,
            \"return_tau\": 7.0,
            \"state_delta\": {}
        }
    d.setdefault(\"dominant_actions\", [])
    d.setdefault(\"support_actions\", [])
    d[\"energy\"] = clamp01(d.get(\"energy\", 0.2))
    d[\"return_tau\"] = float(d.get(\"return_tau\", 7.0))
    if d[\"return_tau\"] < 1.0: d[\"return_tau\"] = 1.0
    if d[\"return_tau\"] > 20.0: d[\"return_tau\"] = 20.0
    d.setdefault(\"state_delta\", {})
    return d

def map_actions_to_channels(decision: Optional[Dict[str, Any]]) -> Dict[str, float]:
    # Massive action space -> stable GPU channels
    targets = {\"warp\":0.0, \"chroma\":0.0, \"grain\":0.0, \"vignette\":0.0, \"energy\":0.2}
    if not decision:
        return targets
    targets[\"energy\"] = float(decision.get(\"energy\", 0.2))

    def ingest(name: str, inten: float, w: float):
        n = (name or \"\").lower()
        inten = clamp01(inten) * w
        if any(k in n for k in [\"warp\",\"liquid\",\"elastic\",\"displace\",\"ripple\",\"shear\",\"parallax\",\"heat\",\"drift\"]):
            targets[\"warp\"] = max(targets[\"warp\"], inten)
        if any(k in n for k in [\"chroma\",\"temperature\",\"color\",\"halation\",\"posterize\",\"desat\"]):
            targets[\"chroma\"] = max(targets[\"chroma\"], inten)
        if any(k in n for k in [\"grain\",\"noise\",\"dust\",\"paper\",\"film\"]):
            targets[\"grain\"] = max(targets[\"grain\"], inten)
        if any(k in n for k in [\"vignette\",\"edge\",\"mask\",\"reveal\"]):
            targets[\"vignette\"] = max(targets[\"vignette\"], inten)

    for a in (decision.get(\"dominant_actions\", []) or [])[:3]:
        if isinstance(a, dict): ingest(a.get(\"action\",\"\"), a.get(\"intensity\",0.0), 1.0)
    for a in (decision.get(\"support_actions\", []) or [])[:12]:
        if isinstance(a, dict): ingest(a.get(\"action\",\"\"), a.get(\"intensity\",0.0), 0.65)

    return targets

def build_user_content(vs: ViewerState, artwork_state: Dict[str, Any]) -> str:
    payload = {
        \"viewer\": {
            \"offset_x\": round(vs.offset_x, 3),
            \"offset_y\": round(vs.offset_y, 3),
            \"distance\": round(vs.distance, 3),
            \"velocity\": round(vs.velocity, 3),
            \"stability\": round(vs.stability, 3),
            \"time_centered\": round(vs.time_centered, 2)
        },
        \"artwork_state\": {
            \"baseline_deviation\": round(float(artwork_state.get(\"baseline_deviation\",0.0)), 3),
            \"energy\": round(float(artwork_state.get(\"energy\",0.2)), 3),
            \"recent_actions\": artwork_state.get(\"recent_actions\", [])[-6:]
        }
    }
    return json.dumps(payload, ensure_ascii=False)

def main():
    cfg = load_json(\"config.json\")
    system_prompt = load_text(\"prompt_system.txt\")

    tracker = HeadTrackerMP(cam_index=0)
    sender  = TDSenderUDP(cfg[\"td_host\"], int(cfg[\"td_port\"]))
    client  = MoonshotClient(model=cfg[\"model\"], temperature=cfg.get(\"temperature\",0.35), max_tokens=cfg.get(\"max_tokens\",300))
    worker  = DecisionWorker(client, system_prompt)
    worker.start()

    decision_hz = float(cfg.get(\"decision_hz\", 2.0))
    decision_period = 1.0 / max(0.5, decision_hz)

    artwork_state = {
        \"baseline_deviation\": 0.0,
        \"energy\": 0.2,
        \"recent_actions\": []
    }

    # Smoothed channels sent to TD
    smooth = {\"warp\":0.0, \"chroma\":0.0, \"grain\":0.0, \"vignette\":0.0, \"energy\":0.2}

    next_decision_t = time.time()

    last_decision = None
    last_t = time.time()

    print(\"Controller running. Start TouchDesigner, run td_build.py once, then keep TD open.\")
    print(\"Press Ctrl+C to stop.\")

    try:
        while True:
            frame, vs = tracker.read()
            now = time.time()
            dt = max(1e-3, now - last_t)
            last_t = now

            # compute baseline deviation from viewer motion (fast, responsive)
            off_mag = (vs.offset_x*vs.offset_x + vs.offset_y*vs.offset_y) ** 0.5
            target_dev = clamp01(off_mag * 1.10 + vs.velocity * 0.55)

            centered = (abs(vs.offset_x) < 0.07) and (abs(vs.offset_y) < 0.07) and (vs.stability > 0.75)

            # FAST ATTACK / SLOW RELEASE on baseline deviation & energy
            if not centered:
                artwork_state[\"baseline_deviation\"] = exp_smooth(artwork_state[\"baseline_deviation\"], target_dev, dt, tau=0.08)  # fast
                artwork_state[\"energy\"] = exp_smooth(artwork_state[\"energy\"], target_dev, dt, tau=0.12)  # fast-ish
            else:
                artwork_state[\"baseline_deviation\"] = exp_smooth(artwork_state[\"baseline_deviation\"], 0.0, dt, tau=0.9)  # slow return
                artwork_state[\"energy\"] = exp_smooth(artwork_state[\"energy\"], 0.15, dt, tau=1.2)  # slow return

            # request AI decision at decision_hz (non-blocking)
            if now >= next_decision_t:
                worker.submit(build_user_content(vs, artwork_state))
                next_decision_t = now + decision_period

            new_dec = worker.get_latest()
            if new_dec is not None:
                last_decision = new_dec

            # map decision -> GPU channels
            targets = map_actions_to_channels(last_decision)

            # Attack/release for channel smoothing
            # If viewer moves fast: attack faster; if centered: release slower
            move_factor = clamp01(vs.velocity * 1.5 + off_mag)
            tau_attack = 0.04 + 0.08*(1.0 - move_factor)  # 40120ms
            tau_release = 0.6 + 1.6*clamp01(vs.time_centered/2.0)  # 0.62.2s

            for k in [\"warp\",\"chroma\",\"grain\",\"vignette\",\"energy\"]:
                tgt = float(targets.get(k, 0.0))
                # scale by artwork_state energy/dev so it calms down when centered
                if k != \"energy\":
                    tgt = clamp01(tgt * (0.25 + 0.75*artwork_state[\"energy\"]) * (0.30 + 0.70*artwork_state[\"baseline_deviation\"]))
                tau = tau_attack if not centered else tau_release
                smooth[k] = exp_smooth(smooth[k], tgt, dt, tau=tau)

            # send to TouchDesigner GPU renderer
            sender.send({
                \"warp\": smooth[\"warp\"],
                \"chroma\": smooth[\"chroma\"],
                \"grain\": smooth[\"grain\"],
                \"vignette\": smooth[\"vignette\"],
                \"energy\": smooth[\"energy\"]
            })

            # limit loop to ~60Hz
            time.sleep(1.0/60.0)

    except KeyboardInterrupt:
        pass
    finally:
        worker.stop()
        tracker.release()

if __name__ == \"__main__\":
    main()
