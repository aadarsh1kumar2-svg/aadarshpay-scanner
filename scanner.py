import os
import imaplib
import email
from email.header import decode_header
import re
import requests

# GitHub Secrets se values aayengi
GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS")
GATEWAY_URL = os.environ.get("GATEWAY_URL")
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET")

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    return re.sub(cleanr, ' ', raw_html)

def process_emails():
    if not all([GMAIL_USER, GMAIL_APP_PASS, GATEWAY_URL, INTERNAL_SECRET]):
        print("Missing environment variables!")
        return

    try:
        # Connect to Gmail
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(GMAIL_USER, GMAIL_APP_PASS)
        mail.select("inbox")

        # Search for UNSEEN emails (jo abhi tak padhe nahi gaye)
        status, messages = mail.search(None, '(UNSEEN)')
        if status != "OK":
            print("No messages found.")
            return

        email_ids = messages[0].split()
        if not email_ids:
            print("No new emails.")
            return

        for e_id in email_ids:
            # Fetch email
            res, msg_data = mail.fetch(e_id, '(RFC822)')
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    # Get Subject
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(encoding if encoding else "utf-8")
                    
                    # Get Body
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() in ["text/plain", "text/html"]:
                                try:
                                    body += part.get_payload(decode=True).decode()
                                except:
                                    pass
                    else:
                        body = msg.get_payload(decode=True).decode()
                    
                    body_clean = clean_html(body)
                    full_text = subject + " " + body_clean

                    # Check if it's a FamPay/Payment email
                    if not re.search(r'(fam|upi|received|credited|paid)', full_text, re.IGNORECASE):
                        continue

                    # Extract Amount (₹123, Rs 123, INR 123)
                    amount_match = re.search(r'(?:₹|Rs\.?|INR)\s*([0-9,]+(?:\.[0-9]{1,2})?)', full_text, re.IGNORECASE)
                    
                    # Extract UTR (12 digit or alphanumeric ref)
                    utr_match = re.search(r'\b([0-9]{12})\b', full_text)
                    if not utr_match:
                        utr_match = re.search(r'(?:UTR|Ref|Txn)\s*[:\-]?\s*([A-Z0-9]{10,18})', full_text, re.IGNORECASE)

                    # Extract Order ID (fg_XXXXX)
                    order_match = re.search(r'\b(fg_[A-Z0-9]{6,12})\b', full_text, re.IGNORECASE)

                    # Extract Sender Name
                    sender_match = re.search(r'from\s+([A-Za-z\s\.]{2,35})(?:\s+on|\s+via|\s+UPI|\.|$)', full_text, re.IGNORECASE)

                    if utr_match and order_match:
                        utr = utr_match.group(1)
                        order_id = order_match.group(1)
                        sender_name = sender_match.group(1).strip() if sender_match else "Verified UPI Payer"
                        
                        print(f"Found Payment -> Order: {order_id}, UTR: {utr}")

                        # Send to your InfinityFree API
                        payload = {
                            "order_id": order_id,
                            "utr": utr,
                            "sender_name": sender_name
                        }
                        headers = {
                            "Content-Type": "application/json",
                            "X-Internal-Secret": INTERNAL_SECRET
                        }
                        
                        api_url = f"{GATEWAY_URL.rstrip('/')}/api/internal/imap-callback.php"
                        try:
                            resp = requests.post(api_url, json=payload, headers=headers, timeout=15)
                            print(f"API Response: {resp.status_code} - {resp.text}")
                            
                            # Mark as read so we don't process it again
                            if resp.status_code == 200:
                                mail.store(e_id, '+FLAGS', '\\Seen')
                        except Exception as e:
                            print(f"Failed to send to API: {e}")
                    
        mail.logout()
    except Exception as e:
        print(f"IMAP Error: {e}")

if __name__ == "__main__":
    process_emails()
