import requests
import os
from datetime import datetime, timedelta

IMWEB_API_KEY = os.environ["IMWEB_API_KEY"]
IMWEB_SECRET_KEY = os.environ["IMWEB_SECRET_KEY"]
SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]


def get_access_token():
    res = requests.get(
        "https://api.imweb.me/v2/auth",
        params={"key": IMWEB_API_KEY, "secret": IMWEB_SECRET_KEY},
    )
    res.raise_for_status()
    data = res.json()
    if data.get("code") != 200:
        raise Exception(f"아임웹 인증 실패: {data}")
    if "data" in data:
        return data["data"]["access_token"]
    return data["access_token"]


def get_monthly_orders(access_token):
    # 지난달 1일 ~ 말일 (KST 기준)
    today = datetime.utcnow() + timedelta(hours=9)
    first_of_this_month = today.replace(day=1)
    last_day_of_last_month = first_of_this_month - timedelta(days=1)
    first_day_of_last_month = last_day_of_last_month.replace(day=1)

    start_date = first_day_of_last_month.strftime("%Y-%m-%d")
    end_date = last_day_of_last_month.strftime("%Y-%m-%d")
    month_label = first_day_of_last_month.strftime("%Y년 %m월")

    print(f"조회 기간: {start_date} ~ {end_date}")

    all_orders = []
    page = 1
    while True:
        res = requests.get(
            "https://api.imweb.me/v2/shop/orders",
            headers={"access-token": access_token},
            params={
                "start_date": start_date,
                "end_date": end_date,
                "limit": 100,
                "page": page,
            },
        )
        res.raise_for_status()
        data = res.json()

        if data.get("code") != 200:
            print(f"주문 조회 응답: {data}")
            break

        orders = data.get("data", {}).get("list", [])
        all_orders.extend(orders)

        total_count = data.get("data", {}).get("total_count", 0)
        if len(all_orders) >= total_count or not orders:
            break
        page += 1

    return all_orders, start_date, end_date, month_label


def calculate_summary(orders):
    total_orders = len(orders)
    total_revenue = 0

    for order in orders:
        payment = order.get("payment", {})
        payment_amount = payment.get("payment_amount", 0) or 0
        total_revenue += int(payment_amount)

    return total_orders, total_revenue


def send_monthly_summary(total_orders, total_revenue, start_date, end_date, month_label):
    period = f"{start_date} ~ {end_date}"
    revenue_str = f"{total_revenue:,}원"
    avg_order = f"{total_revenue // total_orders:,}원" if total_orders else "0원"

    payload = {
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"월간 주문 리포트 — {month_label}"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{period}* 한 달간 결과입니다."},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*주문 수*\n{total_orders}건"},
                    {"type": "mrkdwn", "text": f"*매출*\n{revenue_str}"},
                    {"type": "mrkdwn", "text": f"*건당 평균*\n{avg_order}"},
                ],
            },
            {"type": "divider"},
        ]
    }

    res = requests.post(SLACK_WEBHOOK_URL, json=payload)
    res.raise_for_status()


def main():
    print(f"[{datetime.utcnow() + timedelta(hours=9):%Y-%m-%d %H:%M:%S}] 월간 리포트 시작")

    token = get_access_token()
    orders, start_date, end_date, month_label = get_monthly_orders(token)

    print(f"조회된 주문 수: {len(orders)}건")

    total_orders, total_revenue = calculate_summary(orders)
    send_monthly_summary(total_orders, total_revenue, start_date, end_date, month_label)

    print(f"리포트 전송 완료 — 주문 {total_orders}건 / 매출 {total_revenue:,}원")


if __name__ == "__main__":
    main()
