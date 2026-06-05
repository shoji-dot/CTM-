import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from sqlalchemy import text
from database import SessionLocal

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "your@gmail.com")
SMTP_PASS = os.getenv("SMTP_PASS", "your_app_password")
FROM_NAME = "販売管理システム"

TEMPLATES = {
    "approval_request": {
        "subject": "【承認依頼】{doc_title}",
        "body": "{name} 様\n\n以下のドキュメントの承認をお願いします。\n\nドキュメント名: {doc_title}\n申請者: {uploader_name}\n申請日時: {created_at}\n\nシステムにログインして承認操作を行ってください。\n"
    },
    "rejected": {
        "subject": "【差し戻し】{doc_title}",
        "body": "{name} 様\n\n以下のドキュメントが差し戻されました。\n\nドキュメント名: {doc_title}\nコメント: {comment}\n\n修正後、再申請してください。\n"
    },
    "approved": {
        "subject": "【承認完了】{doc_title}",
        "body": "{name} 様\n\n以下のドキュメントが承認されました。\n\nドキュメント名: {doc_title}\n承認完了日時: {approved_at}\n"
    },
    "reminder": {
        "subject": "【リマインド】承認待ちドキュメントがあります",
        "body": "{name} 様\n\n承認待ちのドキュメントがあります。\n\nドキュメント名: {doc_title}\n申請日時: {created_at}\n\nシステムにログインして承認操作を行ってください。\n"
    }
}


def send_email(to_email: str, subject: str, body: str, html_body: str = None) -> bool:
    """メール送信。html_body指定時はHTML形式で送信。to_emailはstr or list[str]。"""
    try:
        recipients = to_email if isinstance(to_email, list) else [to_email]
        msg = MIMEMultipart("alternative")
        msg['From'] = f"{FROM_NAME} <{SMTP_USER}>"
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = subject
        if html_body:
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        else:
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"メール送信エラー: {e}")
        return False


def _row(row):
    return dict(row._mapping)


def process_pending_notifications():
    db = SessionLocal()
    try:
        pending = [_row(r) for r in db.execute(text("""
            SELECT n.*, d.title as doc_title, d.comment as doc_comment,
                   d.created_at as doc_created_at, d.updated_at as doc_updated_at,
                   s.name as recipient_name, s.email as recipient_email,
                   up.name as uploader_name
            FROM notifications n
            JOIN documents d ON n.document_id = d.id
            JOIN staffs s ON n.recipient_id = s.id
            JOIN staffs up ON d.uploaded_by = up.id
            WHERE n.is_sent = FALSE AND n.document_id IS NOT NULL
        """)).fetchall()]

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
                uploader_name=notif.get('uploader_name', ''),
                created_at=notif['doc_created_at'],
                comment=notif.get('doc_comment') or '',
                approved_at=notif['doc_updated_at'],
            )
            if send_email(notif['recipient_email'], subject, body):
                db.execute(
                    text("UPDATE notifications SET is_sent=TRUE, sent_at=:t WHERE id=:i"),
                    {"t": datetime.now().strftime('%Y-%m-%d %H:%M:%S'), "i": notif['id']}
                )
                sent_count += 1
        db.commit()
        print(f"通知送信完了: {sent_count}件")
        return sent_count
    except Exception as e:
        db.rollback()
        print(f"[process_pending_notifications] {e}")
        return 0
    finally:
        db.close()


def send_reminders():
    db = SessionLocal()
    try:
        docs = [_row(r) for r in db.execute(text("""
            SELECT d.*, dt.name as type_name, up.name as uploader_name, af.id as flow_id
            FROM documents d
            JOIN document_types dt ON d.document_type_id = dt.id
            JOIN staffs up ON d.uploaded_by = up.id
            JOIN approval_flows af ON af.document_type_id = d.document_type_id AND af.is_active=TRUE
            WHERE d.status = 'in_review'
        """)).fetchall()]

        for doc in docs:
            step = db.execute(text("""
                SELECT ast.*, s.name as approver_name, s.email as approver_email
                FROM approval_steps ast
                LEFT JOIN staffs s ON ast.approver_id = s.id
                WHERE ast.flow_id=:f AND ast.step_order=:s
            """), {"f": doc['flow_id'], "s": doc['current_step']}).fetchone()

            if not step or not step._mapping.get('approver_email'):
                continue
            assignee_id = step._mapping.get('approver_id')
            if not assignee_id:
                continue
            try:
                db.execute(
                    text("INSERT INTO notifications (document_id, recipient_id, type) VALUES (:d,:r,'reminder')"),
                    {"d": doc["id"], "r": assignee_id},
                )
                db.commit()
            except Exception as e:
                db.rollback()
                print(f"[reminder] {e}")
    finally:
        db.close()
