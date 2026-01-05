import json, time, threading, os
from queue import Queue, Empty
from moonshot_client import MoonshotClient
from td_sender import TDSenderUDP
from head_tracker_mp import HeadTrackerMP

def load_json(path):
    with open(path, 'r', encoding='utf-8-sig') as f: return json.load(f)

def load_text(path):
    with open(path, 'r', encoding='utf-8-sig') as f: return f.read()

def exp_smooth(cur, tgt, dt, tau):
    return float(cur + (tgt - cur) * (1.0 - pow(2.718, -dt / max(0.02, tau))))

class DecisionWorker(threading.Thread):
    def __init__(self, client, prompt):
        super().__init__(daemon=True)
        self.client, self.prompt, self.in_q, self.out_q = client, prompt, Queue(1), Queue(1)
    def run(self):
        while True:
            try:
                content = self.in_q.get()
                res = self.client.chat_json(self.prompt, content)
                self.out_q.put(res)
            except: pass

def main():
    cfg = load_json("config.json")
    worker = DecisionWorker(MoonshotClient(model=cfg["model"]), load_text("prompt_system.txt"))
    worker.start()
    tracker = HeadTrackerMP(0)
    sender = TDSenderUDP(cfg["td_host"], cfg["td_port"])
    
    smooth = {"warp":0.0, "chroma":0.0, "grain":0.0, "vignette":0.0, "energy":0.2, "break":0.0}
    mood_state = {"instability":0.2, "entropy":0.1, "amnesia":0.5, "gravity":0.5, "break": 0.0}
    last_t = time.time()

    while True:
        frame, vs = tracker.read()
        now = time.time()
        dt, last_t = now - last_t, now
        
        if not worker.in_q.full():
            worker.in_q.put(json.dumps({"viewer": vs.__dict__}))
        try:
            new_mood = worker.out_q.get_nowait()
            mood_state.update({k: new_mood[k] for k in mood_state if k in new_mood})
        except Empty: pass

        # Agency: Se l'osservatore è troppo statico (> 10s), forza un evento di rottura
        break_trigger = 1.0 if vs.time_centered > 10.0 else 0.0
        
        off_mag = (vs.offset_x**2 + vs.offset_y**2)**0.5
        target_warp = off_mag * mood_state["instability"] * 1.5
        
        tau_rel = 2.0 * (1.0 - mood_state["amnesia"]) + 0.1
        tau = 0.1 if off_mag > 0.1 else tau_rel

        smooth["warp"] = exp_smooth(smooth["warp"], target_warp, dt, tau)
        smooth["grain"] = exp_smooth(smooth["grain"], mood_state["entropy"], dt, 0.5)
        smooth["break"] = exp_smooth(smooth["break"], break_trigger, dt, 0.05) # Attacco rapido

        sender.send(smooth)
        time.sleep(0.016)

if __name__ == "__main__": main()
