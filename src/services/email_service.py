import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any
from config import settings

class EmailAlertService:
    def send_opportunity_alert(self, rfp_data: Dict[str, Any], eval_res: Dict[str, Any]) -> bool:
        if not settings.SMTP_HOST or not settings.SMTP_USER:
            print(f"[EmailAlertService] SMTP not configured. Logged alert for: {rfp_data.get('title')}")
            return False

        try:
            msg = MIMEMultipart("alternative")
            score = eval_res.get("relevance_score", 0)
            rec = eval_res.get("recommendation", "PURSUE")
            title = rfp_data.get("title", "")

            msg["Subject"] = f"[{rec}] [{score}% MATCH] {title[:60]}"
            msg["From"] = settings.SMTP_USER
            msg["To"] = settings.ALERT_EMAIL_TO

            deliverables_html = "".join(f"<li>{d}</li>" for d in eval_res.get("eai_deliverables", []))
            gaps_html = "".join(f"<li>{g}</li>" for g in eval_res.get("missing_requirements", []))

            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
                <div style="background-color: #0f172a; padding: 20px; color: #fff; border-radius: 8px 8px 0 0;">
                    <h2 style="margin: 0; color: #38bdf8;">EAI Systems RFP Intelligence Alert</h2>
                    <p style="margin: 5px 0 0 0; color: #94a3b8;">High-Probability Opportunity Identified</p>
                </div>
                <div style="padding: 20px; border: 1px solid #cbd5e1; border-top: none; border-radius: 0 0 8px 8px;">
                    <table style="width: 100%; margin-bottom: 20px;">
                        <tr>
                            <td><strong>Title:</strong> {title}</td>
                        </tr>
                        <tr>
                            <td><strong>Issuing Body:</strong> {rfp_data.get('issuing_org')} ({rfp_data.get('country')})</td>
                        </tr>
                        <tr>
                            <td><strong>Submission Deadline:</strong> {rfp_data.get('submission_deadline')}</td>
                        </tr>
                        <tr>
                            <td><strong>Relevance Score:</strong> <span style="font-weight: bold; color: #16a34a;">{score}%</span> ({rec})</td>
                        </tr>
                    </table>

                    <h3 style="color: #0f172a;">Executive Summary</h3>
                    <p>{eval_res.get('ai_summary')}</p>

                    <h3 style="color: #0f172a;">Why Relevant</h3>
                    <p>{eval_res.get('why_relevant')}</p>

                    <h3 style="color: #16a34a;">EAI / PhantomOps Proposed Deliverables</h3>
                    <ul>{deliverables_html}</ul>

                    <h3 style="color: #dc2626;">Requirements Gaps / Partnering Needed</h3>
                    <ul>{gaps_html}</ul>

                    <div style="margin-top: 25px;">
                        <a href="{rfp_data.get('source_url')}" style="background-color: #2563eb; color: #fff; padding: 10px 18px; text-decoration: none; border-radius: 5px; font-weight: bold;">Open Original Procurement Notice Page</a>
                    </div>
                </div>
            </body>
            </html>
            """
            msg.attach(MIMEText(html_content, "html"))

            with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
                server.starttls()
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                server.send_message(msg)

            print(f"[EmailAlertService] Alert sent successfully for: {title[:50]}")
            return True
        except Exception as e:
            print(f"[EmailAlertService] Failed to send email alert: {e}")
            return False
