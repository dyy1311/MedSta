"""015-017 e2e 冒烟（精简）。"""
import asyncio, json, urllib.request

BASE = "http://localhost:8032"
CSV = b"group,age,score\nA,25,3.1\nA,31,4.2\nA,42,3.8\nB,38,5.0\nB,51,4.4\nB,47,3.9\n"


def post(url, data=None, files=None):
    if files:
        b = "----medsta"
        n, fn, c = files
        body = (f"--{b}\r\nContent-Disposition: form-data; name=\"{n}\"; filename=\"{fn}\"\r\n"
                f"Content-Type: text/csv\r\n\r\n").encode() + c + f"\r\n--{b}--\r\n".encode()
        req = urllib.request.Request(url, data=body,
                                     headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    else:
        req = urllib.request.Request(url, data=json.dumps(data).encode(),
                                     headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req).read())


async def main():
    import websockets
    sid = post(f"{BASE}/sessions")["session_id"]
    up = post(f"{BASE}/sessions/{sid}/data", files=("file", "cohort.csv", CSV))
    print("1) upload confirmed:", up.get("type_confirmed"))
    async with websockets.connect(f"ws://localhost:8032/ws/{sid}") as ws:
        await ws.send(json.dumps({"type": "chat", "content": "比较两组年龄差异"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), 30))
        print("2)", msg["type"], [c["name"] for c in msg.get("columns", [])])
        assert msg["type"] == "type_review"
        types = {c["name"]: ("categorical" if c["name"] == "group" else "continuous")
                 for c in msg["columns"]}
        await ws.send(json.dumps({"type": "type_confirm", "types": types}))
        while True:
            msg = json.loads(await asyncio.wait_for(ws.recv(), 300))
            if msg["type"] in ("type_confirmed", "progress", "stream"):
                continue
            break
        print("3)", msg["type"])
        if msg["type"] == "error":
            print(str(msg)[:200]); return
        cid = next(o["id"] for o in msg["options"] if o["action"] == "confirm")
        await ws.send(json.dumps({"type": "option", "option_id": cid}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), 60))
        print("4) confirm ->", msg["type"])
        step_index = None
        await ws.send(json.dumps({
            "type": "chart_choice", "use_default": True,
            "layout": "separate", "alpha": 0.05, "correction": "holm",
        }))
        print("4.5) chart_choice sent")
        last_report = None
        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), 75)
            except asyncio.TimeoutError:
                print("4.9) recv idle"); break
            print("recv frame:", str(raw)[:50])
            msg = json.loads(raw)
            if msg["type"] == "review_request":
                last_report = msg["report"]
            if msg["type"] == "plot_suggest":
                step_index = msg["steps"][0]["step_index"]
                print("5) plot_suggest:", [(x["title"], x["charts"][:2]) for x in msg["steps"]])
                await ws.send(json.dumps({"type": "plot_later", "step_index": step_index,
                                          "chart_type": msg["steps"][0]["charts"][0]}))
                continue
            if msg["type"] == "error":
                print("ERR:", msg["code"], str(msg)[:150]); return
        assert last_report, "未收到执行报告"
        with_table = [i for i, s_ in enumerate(last_report["steps"]) if s_.get("table")]
        print("5b) table steps:", with_table)
        step_index = with_table[0]
        await ws.send(json.dumps({"type": "review", "decision": "accept"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), 60))
        print("7) final:", msg["type"])
        print("8) export:", urllib.request.urlopen(
            f"{BASE}/export/{sid}/{step_index}?format=csv").status)
        return

asyncio.run(main())
