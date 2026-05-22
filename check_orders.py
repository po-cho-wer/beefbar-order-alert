import requests
import os
from datetime import datetime, timedelta, timezone

IMWEB_API_KEY = os.environ["IMWEB_API_KEY"]
IMWEB_SECRET_KEY = os.environ["IMWEB_SECRET_KEY"]
SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]

LOOKBACK_MINUTES = 11  # 10분 간격 실행 + 1분 여유
KST = timezone(timedelta(hours=9))


def get_access_token():
    res = requests.get(
        "https://api.imweb.me/v2/auth",
        params={"key": IMWEB_API_KEY, "secret": IMWEB_SECRET_KEY},
    )
    res.raise_for_status()
    data = res.json()
    print(f"아임웹 인증 응답: {data}")
    if data.get("code") != 200:
        raise Exception(f"아임웹 인증 실패: {data}")
    # 응답 구조: {"code":200, "data": {"access_token":...}} 또는 {"code":200, "access_token":...}
    if "data" in data:
        return data["data"]["access_token"]
    return data["access_token"]


def get_recent_orders(access_token):
    now_utc = datetime.now(timezone.utc)
    cutoff_utc = now_utc - timedelta(minutes=LOOKBACK_MINUTES)

    # 아임웹은 KST 기준 — 날짜 경계 오류 방지를 위해 어제(KST)부터 조회
    now_kst = now_utc.astimezone(KST)
    yesterday_kst = (now_kst - timedelta(days=1)).strftime("%Y-%m-%d")
    today_kst = now_kst.strftime("%Y-%m-%d")

    res = requests.get(
        "https://api.imweb.me/v2/shop/orders",
        headers={"access-token": access_token},
        params={
            "start_date": yesterday_kst,
            "end_date": today_kst,
            "limit": 100,
            "page": 1,
        },
    )
    res.raise_for_status()
    data = res.json()

    if data.get("code") != 200:
        print(f"주문 조회 응답: {data}")
        return []

    orders = data.get("data", {}).get("list", [])

    cutoff_ts = cutoff_utc.timestamp()
    recent = []
    for order in orders:
        order_time = order.get("order_time", 0)
        if isinstance(order_time, (int, float)) and order_time > 0:
            # Unix timestamp은 UTC 절대값이므로 직접 비교
            if order_time >= cutoff_ts:
                recent.append(order)
        elif isinstance(order_time, str):
            try:
                # 아임웹 문자열은 KST 기준 → KST aware로 파싱 후 비교
                ot_kst = datetime.strptime(order_time[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
                if ot_kst >= cutoff_utc:
                    recent.append(order)
            except ValueError:
                recent.append(order)

    return recent


STATUS_LABELS = {
    "order": "주문 완료",
    "pay_done": "결제 완료",
    "ready": "상품 준비 중",
    "delivery": "배송 중",
    "delivery_done": "배송 완료",
    "cancel_request": "취소 요청",
    "cancel": "주문 취소",
    "cancel_done": "취소 완료",
    "refund_request": "환불 요청",
    "refund": "환불 중",
    "refund_done": "환불 완료",
}

CANCEL_STATUSES = {"cancel_request", "cancel", "cancel_done", "refund_request", "refund", "refund_done"}


def format_order_message(order):
    order_code = order.get("order_code", "N/A")
    pay_price = order.get("pay_price", 0)
    orderer = order.get("orderer", {})
    orderer_name = orderer.get("name", "알 수 없음")
    order_status = str(order.get("order_status", "")).lower()

    items = order.get("items", [])
    item_names = [item.get("prod_name", "") for item in items[:3]]
    items_str = ", ".join(filter(None, item_names)) or "상품 정보 없음"
    if len(items) > 3:
        items_str += f" 외 {len(items) - 3}개"

    price_str = f"{int(pay_price):,}원"
    status_label = STATUS_LABELS.get(order_status, order_status or "알 수 없음")
    is_cancel = order_status in CANCEL_STATUSES
    header_text = f"주문 취소 알림 — {order_code}" if is_cancel else "새 주문이 들어왔어요!"

    return {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": header_text},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*주문번호*\n{order_code}"},
                    {"type": "mrkdwn", "text": f"*상태*\n{status_label}"},
                    {"type": "mrkdwn", "text": f"*결제금액*\n{price_str}"},
                    {"type": "mrkdwn", "text": f"*주문자*\n{orderer_name}"},
                    {"type": "mrkdwn", "text": f"*상품*\n{items_str}"},
                ],
            },
            {"type": "divider"},
        ]
    }


def send_slack(payload):
    res = requests.post(SLACK_WEBHOOK_URL, json=payload)
    res.raise_for_status()


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 주문 확인 시작")

    token = get_access_token()
    orders = get_recent_orders(token)

    print(f"최근 {LOOKBACK_MINUTES}분 신규 주문: {len(orders)}건")

    for order in orders:
        msg = format_order_message(order)
        send_slack(msg)
        print(f"알림 전송 완료: {order.get('order_code')}")

    if not orders:
        print("새 주문 없음")


if __name__ == "__main__":
    main()
