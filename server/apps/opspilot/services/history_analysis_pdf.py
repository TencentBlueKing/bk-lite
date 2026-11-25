from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate

CHANNEL_LABELS = {
    "platform": ("平台", "Platform"),
    "workflow": ("编排中心", "Workflow"),
    "workbench": ("工作台", "Workbench"),
    "web_chat": ("Web 对话", "Web Chat"),
    "embedded_chat": ("嵌入式对话", "Embedded Chat"),
    "enterprise_wechat": ("企微应用", "Enterprise WeChat"),
    "enterprise_wechat_aibot": ("企微机器人", "Enterprise WeChat AI Bot"),
    "dingtalk": ("钉钉", "DingTalk"),
    "feishu": ("飞书", "Feishu"),
    "wechat_official": ("微信公众号", "WeChat Official Account"),
}


def render_analysis_pdf(task):
    font = "STSong-Light"
    pdfmetrics.registerFont(UnicodeCIDFont(font))
    english = task.locale == "en"
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, title=task.name, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=48)
    story = []

    def paragraph(text, size=11, color="#182230"):
        style = ParagraphStyle("report", fontName=font, fontSize=size, leading=size * 1.5, spaceAfter=8, textColor=HexColor(color), wordWrap="CJK")
        story.append(Paragraph(escape(str(text)).replace("\n", "<br/>"), style))

    paragraph(task.name, 21)
    paragraph(task.skill.name, 14)
    objectives = {"overview": ("综合分析", "Overview"), "needs": ("高频需求", "Recurring needs"), "quality": ("回答质量", "Answer quality")}
    paragraph(objectives[task.objective][int(english)])
    if task.focus:
        paragraph(task.focus)
    scope = task.scope
    if scope["scope"] == "range":
        paragraph(f"{scope['start']} — {scope['end']}")
        if scope.get("person"):
            paragraph(("User filter" if english else "用户筛选") + " · " + scope["person"])
        if scope.get("channel_id"):
            paragraph(("Channel" if english else "渠道") + f" #{scope['channel_id']}")
    else:
        paragraph("Selected conversations" if english else "指定对话")
    if scope.get("channel_types"):
        labels = [CHANNEL_LABELS.get(kind, (kind, kind))[int(english)] for kind in scope["channel_types"]]
        paragraph(("Channels" if english else "渠道") + " · " + " / ".join(labels))
    paragraph(
        f"{task.conversation_count} conversations · {task.question_count} user questions"
        if english
        else f"覆盖 {task.conversation_count} 个对话，{task.question_count} 条用户提问"
    )
    paragraph(f"{task.creator} · {task.created_at:%Y-%m-%d %H:%M %Z}", 10)
    for item in task.findings:
        paragraph(item["finding"], 14)
        paragraph(("Suggestion · " if english else "建议 · ") + item["suggestion"])
        refs = ", ".join(f"#{ref['message_id']}" for ref in item["evidence"])
        paragraph(("Evidence · " if english else "证据消息 · ") + refs, 10, "#485466")
    doc.build(story)
    return buffer.getvalue()
