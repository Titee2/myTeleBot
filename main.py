import requests

BOT_TOKEN = "8416188460:AAFsMnrI-XImYz7HjNx7SXnAO9EAsDFd_5s"
CHAT_ID = "7897793877"

r = requests.post(
    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
    json={"chat_id": CHAT_ID, "text": "✅ Telegram test OK"}
)

print(r.status_code, r.text)
