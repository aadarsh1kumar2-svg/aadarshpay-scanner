import os
import imaplib
import email
from email.header import decode_header
import re
import requests
import threading
import time
from flask import Flask

app = Flask(__name__)

# GitHub/Render Secrets se values aayengi
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS")
GATEWAY_URL = os.environ.get("GATEWAY_URL")
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET")

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, ' ', raw_html)

def scan_gmail():
    while True: # Har 30 second mein check karega
        try:
            if not all([GMAIL_USER, GMAIL_APP_PASS, GATEWAY_URL, INTERNAL_SECRET]):
                print("Missing environment variables!")
                time.sleep(30)
                continue

            print("Checking Gmail...")
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(GMAIL_USER, GMAIL_APP_PASS)
            mail.select("inbox")

            status, messages = mail.search(None, '(UNSEEN)')
            if status == "OK" and messages[0]:
                email_ids = messages[0].split()
                for e_id in email_ids:
                    res, msg_data = mail.fetch(e_id, '(RFC822)')
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            subject, encoding = decode_header(msg["Subject"])[0]
                            if isinstance(subject, bytes):
                                subject = subject.decode(encoding if encoding else "utf-8")
                            
                            body = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() in ["text/plain", "text/html"]:
                                        try: body += part.get_payload(decode=True).decode()
                                        except: pass
                            else:
                                body = msg.get_payload(decode=True).decode()
                            
                            body_clean = clean_html(body)
                            full_text = subject + " " + body_clean

                            if not re.search(r'(fam|upi|received|credited|paid)', full_text, re.IGNORECASE):
                                continue

                            utr_match = re.search(r'\b([0-9]{12})\b', full_text) or re.search(r'(?:UTR|Ref|Txn)\s*[:\-]?\s*([A-Z0-9]{10,18})', full_text, re.IGNORECASE)
                            order_match = re.search(r'\b(fg_[A-Z0-9]{6,12})\b', full_text, re.IGNORECASE)
                            sender_match = re.search(r'from\s+([A-Za-z\s\.]{2,35})(?:\s+on|\s+via|\s+UPI|\.|$)', full_text, re.IGNORECASE)

                            if utr_match and order_match:
                                utr = utr_match.group(1)
                                order_id = order_match.group(1)
                                sender_name = sender_match.group(1).strip() if sender_match else "Verified UPI Payer"
                                
                                print(f"Found Payment -> Order: {order_id}, UTR: {utr}")

                                payload = {"order_id": order_id, "utr": utr, "sender_name": sender_name}
                                headers = {"Content-Type": "application/json", "X-Internal-Secret": INTERNAL_SECRET}
                                api_url = f"{GATEWAY_URL.rstrip('/')}/api/internal/imap-callback.php"
                                
                                resp = requests.post(api_url, json=payload, headers=headers, timeout=15)
                                print(f"API Response: {resp.status_code} - {resp.text}")
                                
                                if resp.status_code == 200:
                                    mail.store(e_id, '+FLAGS', '\\Seen')
            mail.logout()
        except Exception as e:
            print(f"Error: {e}")
        
        time.sleep(30) # 30 second wait karega agle check se pehle

# Web server route (Render ko zinda rakhne ke liye)
@app.route('/')
def home():
    return "AadarshPay Scanner is running live!"

if __name__ == "__main__":
    # Scanner ko background thread mein chalao
    threading.Thread(target=scan_gmail, daemon=True).start()
    # Web server start karo
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
