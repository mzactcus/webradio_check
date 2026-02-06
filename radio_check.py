import requests
import json
import os
from datetime import datetime

TIMEOUT = 20
HISTORY_FILE = "data/history.json"

STATIONS = [
    {
        "id": "SUEDTIROL_1",
        "query": {"name": "Südtirol 1", "codec": "mp3", "limit": 20}
    },
    # weitere Sender hier hinzufügen
]

def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_history(history):
    os.makedirs("data", exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def check_stream(url):
    try:
        r = requests.get(
            url,
            stream=True,
            timeout=(15, TIMEOUT),
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Webradio-Monitor)"}
        )
        chunk = next(r.iter_content(chunk_size=4096), None)
        return {
            "ok": r.status_code == 200 and chunk is not None,
            "status": r.status_code,
            "final_url": r.url,
            "content_type": r.headers.get("Content-Type", ""),
            "received_bytes": len(chunk) if chunk else 0
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}

def determine_status(fail_count):
    if fail_count == 0:
        return "stable"   # 🟢
    elif fail_count <= 2:
        return "unstable" # 🟡
    else:
        return "dead"     # 🔴

def main():
    history = load_history()
    now = datetime.utcnow().isoformat() + "Z"

    for station in STATIONS:
        sid = station["id"]
        payload = station["query"]

        # Radio Browser POST
        try:
            resp = requests.post(
                "http://all.api.radio-browser.info/json/stations/search",
                headers={"Content-Type": "application/json"},
                data=json.dumps(payload),
                timeout=TIMEOUT
            )
            entries = resp.json()
        except Exception as e:
            print(f"[{now}] Fehler Radio Browser für {sid}: {e}")
            # optional: log radio-browser error to history
            history.setdefault(sid, [])
            last_fail = history[sid][-1].get("fail_count", 0) if history[sid] else 0
            fail_count = last_fail + 1
            status = determine_status(fail_count)
            history[sid].append({
                "timestamp": now,
                "searched_url": None,
                "final_url": None,
                "ok": False,
                "fail_count": fail_count,
                "status": status,
                "status_icon": {"stable":"🟢","unstable":"🟡","dead":"🔴"}[status],
                "http_status": None,
                "content_type": None,
                "received_bytes": 0,
                "error": f"radio_browser_error: {str(e)}"
            })
            continue

        # deduplizieren nach url_resolved
        urls = list({e.get("url_resolved") for e in entries if e.get("url_resolved")})

        # Wenn keine URL gefunden wurde -> loggen
        if not urls:
            print(f"[{now}] Keine Streaming-URL gefunden für {sid} (search: {payload})")
            history.setdefault(sid, [])
            last_fail = history[sid][-1].get("fail_count", 0) if history[sid] else 0
            fail_count = last_fail + 1
            status = determine_status(fail_count)
            history[sid].append({
                "timestamp": now,
                "searched_url": None,
                "final_url": None,
                "ok": False,
                "fail_count": fail_count,
                "status": status,
                "status_icon": {"stable":"🟢","unstable":"🟡","dead":"🔴"}[status],
                "http_status": None,
                "content_type": None,
                "received_bytes": 0,
                "error": "no_streaming_url_found"
            })
            # weiter zur nächsten Station
            continue

        for url in urls:
            result = check_stream(url)

            # History initialisieren
            history.setdefault(sid, [])
            # Fail-Counter berechnen (nur für gleiche final_url)
            prev_entries = [e for e in history[sid] if e.get("final_url") == result.get("final_url")]
            fail_count = 0
            if prev_entries:
                last_ok = prev_entries[-1]["ok"]
                fail_count = prev_entries[-1].get("fail_count", 0)
                if not result["ok"]:
                    fail_count += 1
                else:
                    fail_count = 0
            else:
                fail_count = 0 if result["ok"] else 1

            status = determine_status(fail_count)

            history[sid].append({
                "timestamp": now,
                "searched_url": url,
                "final_url": result.get("final_url"),
                "ok": result.get("ok"),
                "fail_count": fail_count,
                "status": status,
                "status_icon": {"stable":"🟢","unstable":"🟡","dead":"🔴"}[status],
                "http_status": result.get("status"),
                "content_type": result.get("content_type"),
                "received_bytes": result.get("received_bytes"),
                "error": result.get("error")
            })

            # Console-Log für GitHub Actions output
            if result.get("ok"):
                print(f"[{now}] {sid} OK -> {result.get('final_url')} ({result.get('content_type')}, {result.get('received_bytes')} bytes)")
            else:
                print(f"[{now}] {sid} FAIL -> searched: {url} final: {result.get('final_url')} error: {result.get('error')} http_status: {result.get('status')}")

    save_history(history)

if __name__ == "__main__":
    main()
