import smtplib
import sqlite3
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ─── SMTP設定（環境変数推奨） ─────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "your@gmail.com")
SMTP_PASS = os.getenv("SMTP_PASS", "your_app_password")
FROM_NAME = "販売管理システム"

DB_PATH = os.path.join(os.path.dirname(__file__), 'sales_app.db')

TEMPLATES = {
    "approval_request": {
        "subject": "【承認依頼】{doc_title}",
        "body": """\
{name} 様

以下のドキュメントの承認をお願いします。

ドキュメント名: {doc_title}
申請者: {uploader_name}
申請日時: {created_at}

システムにログインして承認操作を行ってください。
"""
    },
    "rejected": {
        "subject": "【差し戻し】{doc_title}",
        "body": """\
{name} 様

以下のドキュメントが差し戻されました。

ドキュメント名: {doc_title}
コメント: {comment}

修正後、再申請してください。
"""
    },
    "approved": {
        "subject": "【承認完了】{doc_title}",
        "body": """\
{name} 様

以下のドキュメントが承認されました。

ドキュメント名: {doc_title}
承認完了日時: {approved_at}
"""
    },
    "reminder": {
        "subject": "【リマインド】承認待ちドキュメントがあります",
        "body": """\
{name} 様

承認待ちのドキュメントがあります。

ドキュメント名: {doc_title}
申請日時: {created_at}

システムにログインして承認操作を行ってください。
"""
    }
}

def send_email(to_email: str, subject: str, body: str) -> bool:
    try:
        msg = MIMEMultipart()
        msg['From'] = f"{FROM_NAME} <{SMTP_USER}>"
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"メール送信エラー: {e}")
        return False

def process_pending_notifications():
    """未送信通知を処理する（定期実行用）"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    pending = conn.execute("""
        SELECT n.*, d.title as doc_title, d.comment as doc_comment,
               d.created_at as doc_created_at, d.updated_at as doc_updated_at,
               s.name as recipient_name, s.email as recipient_email,
               up.name as uploader_name
        FROM notifications n
        JOIN documents d ON n.document_id = d.id
        JOIN staffs s ON n.recipient_id = s.id
        JOIN staffs up ON d.uploaded_by = up.id
        WHERE n.is_sent = 0
    """).fetchall()

    sent_count = 0
    for notif in pending:
        if not notif['recipient_email']:
            continue

        tmpl = TEMPLATES.get(notif['type'])
        if not tmpl:
            continue

        subject = tmpl['subject'].format(doc_title=notif['doc_title'])
        body = tmpl['body'].format(
            name=notif['recipient_name'],
            doc_title=notif['doc_title'],
            uploader_name=notif['uploader_name'],
            created_at=notif['doc_created_at'],
            comment=notif['doc_comment'] or '',
            approved_at=notif['doc_updated_at'],
        )

        if send_email(notif['recipient_email'], subject, body):
            conn.execute("""
                UPDATE notifications SET is_sent=1, sent_at=? WHERE id=?
            """, (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), notif['id']))
            sent_count += 1

    conn.commit()
    conn.close()
    print(f"通知送信完了: {sent_count}件")
    return sent_count

def send_reminders():
    """承認待ち通知のリマインド送信"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row

    # 承認中ドキュメントを取得
    docs = conn.execute("""
        SELECT d.*, dt.name as type_name, up.name as uploader_name,
               af.id as flow_id
        FROM documents d
        JOIN document_types dt ON d.document_type_id = dt.id
        JOIN staffs up ON d.uploaded_by = up.id
        JOIN approval_flows af ON af.document_type_id = d.document_type_id AND af.is_active=1
        WHERE d.status = 'in_review'
    """).fetchall()

    for doc in docs:
        # 現在の承認者を取得
        step = conn.execute("""
            SELECT ast.*, s.name as approver_name, s.email as approver_email
            FROM approval_steps ast
            LEFT JOIN staffs s ON ast.approver_id = s.id
            WHERE ast.flow_id=? AND ast.step_order=?
        """, (doc['flow_id'], doc['current_step'])).fetchone()

        if not step or not step['approver_email']:
            continue

        # リマインド通知を作成
        conn.execute("""
            INSERT INTO notifications (document_id, recipient_id, type)
            VALUES (?,?,'reminder')
        """, (doc['id'], step['approver_id']))

    conn.commit()
    conn.close()
    process_pending_notifications()

if __name__ == '__main__':
    process_pending_notifications()
