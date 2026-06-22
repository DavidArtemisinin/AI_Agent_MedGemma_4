import os
import json
import base64
import uuid
import time
import requests

# ================= Configuration =================
# 建議你優先用 webhook-test 做開發；要長期 demo 再換 production webhook
# Please be advised, that the {YOUR_EDGE_AI_DEVICE_IP} should be changed to your actual ip address and the webhook url should be the same as the n8n webhook-test session shown.
WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "http://{YOUR_EDGE_AI_DEVICE_IP}:{PORT}/{WEBHOOK_PATH}")

IMAGE_FILENAME = os.environ.get("XRAY_IMAGE", "xray_sample.png")

# Edge / Jetson 類環境建議加 timeout + retry，避免偶發網路/工作流延遲就當機
TIMEOUT_SEC = float(os.environ.get("HTTP_TIMEOUT", "60"))
RETRY = int(os.environ.get("HTTP_RETRY", "2"))
RETRY_BACKOFF_SEC = float(os.environ.get("HTTP_RETRY_BACKOFF", "1.5"))
# =================================================


def get_image_path(filename: str) -> str:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, filename)


def encode_image_b64(image_path: str) -> str:
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found! Please check the path: {image_path}")

    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def post_with_retry(url: str, payload: dict) -> requests.Response:
    last_exc = None
    for attempt in range(RETRY + 1):
        try:
            # json=payload 會自動設定 Content-Type: application/json
            return requests.post(url, json=payload, timeout=TIMEOUT_SEC)
        except Exception as e:
            last_exc = e
            if attempt < RETRY:
                sleep_s = RETRY_BACKOFF_SEC * (attempt + 1)
                print(f"[WARN] POST failed (attempt {attempt+1}/{RETRY+1}): {e}. Retrying in {sleep_s:.1f}s ...")
                time.sleep(sleep_s)
    raise last_exc


def safe_parse_response(resp: requests.Response) -> dict:
    """
    # 盡量把回應解析成 JSON；如果不是 JSON，也會把原文保留下來，
    # 避免你之前遇到的 'Expecting value: line 1 column 1 (char 0)' 直接炸掉。
    """
    result = {
        "status_code": resp.status_code,
        "content_type": resp.headers.get("content-type", ""),
        "text": None,
        "json": None,
    }

    # 一定先把 raw text 留下來（debug 超重要）
    try:
        result["text"] = resp.text
    except Exception:
        result["text"] = "<unable to read resp.text>"

    # 再嘗試 JSON
    try:
        result["json"] = resp.json()
    except Exception:
        result["json"] = None

    return result


def build_payload(img_b64: str) -> dict:
    """
    # 方法 A：影像品質檢查 demo payload
    """
    return {
        "request_id": str(uuid.uuid4()),
        "task": "xray_quality_check",
        "query": (
            "Demo task: Assess ONLY technical/quality aspects of this image and write out the assessment result in natural paragraphs format. "
            "Do NOT interpret medical findings, do NOT diagnose, and do NOT give medical advice, BUT take into account the body section the image shows. "
            "Output JSON."
        ),
        "output_schema": {
            "modality": "string",
            "view_guess": "string",
            "quality_issues": ["string"],
            "confidence": "number",
            "limitations": "string"
        },
        "history": "De-identified demo input. No clinical context. Evaluate image quality only.",
        "image_b64": img_b64
    }


if __name__ == "__main__":
    req_id = str(uuid.uuid4())
    img_path = get_image_path(IMAGE_FILENAME)

    print(f"[{req_id}] Reading image: {img_path}")
    img_b64 = encode_image_b64(img_path)

    payload = build_payload(img_b64)

    print(f"[{req_id}] POST -> {WEBHOOK_URL}")
    print("(Make sure n8n is listening if you're using webhook-test.)")

    resp = post_with_retry(WEBHOOK_URL, payload)
    parsed = safe_parse_response(resp)

    print(f"\n[{req_id}] === RESPONSE SUMMARY ===")
    print(f"Status: {parsed['status_code']}")
    print(f"Content-Type: {parsed['content_type']}")

    if parsed["json"] is not None:
        print("\nJSON:")
        print(json.dumps(parsed["json"], indent=2, ensure_ascii=False))
    else:
        print("\nResponse is NOT JSON. Raw text:")
        print(parsed["text"])
