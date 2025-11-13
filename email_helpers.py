from __future__ import annotations
from pydantic import BaseModel

"""Utility helpers for sending approval emails."""

import shutil
import smtplib
import subprocess
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Iterable, Tuple
import re


def send_email(
    *,
    smtp_host: str,
    smtp_port: int,
    username: str | None,
    password: str | None,
    use_tls: bool,
    subject: str,
    body: str,
    sender: str,
    recipients: Iterable[str],
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    html_body = body
    plain_body = re.sub(r"<[^>]+>", "", html_body)
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    if use_tls:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
    else:
        server = smtplib.SMTP_SSL(smtp_host, smtp_port)

    with server:
        if username and password:
            server.login(username, password)
        server.send_message(msg)


def markdown_to_text(markdown: str) -> str:
    """Convert Markdown to html text via pandoc with regex fallback."""
    pandoc = shutil.which("pandoc")
    if pandoc:
        try:
            proc = subprocess.run(
                [pandoc, "-f", "markdown", "-t", "plain"],
                input=markdown.encode("utf-8"),
                capture_output=True,
                check=True,
            )
            text = proc.stdout.decode("utf-8").strip()
            if text:
                return text
        except subprocess.SubprocessError:
            pass

    text = markdown
    text = re.sub(r"```[\s\S]*?```", "", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"^\s{0,3}[-*+]\s+", "- ", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}\d+[.)]\s+", "- ", text, flags=re.MULTILINE)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 (\2)", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


__all__ = ["send_email", "markdown_to_text", "prep_email_with_openai"]




def prep_email_with_openai(
    *,
    client,
    model: str,
    system_prompt: str,
    newsletter_markdown: str,
) -> Tuple[str, str]:

    base_instructions = (
        "You are an email assistant. Given newsletter Markdown that contains headings"
        " like 'Subject:' and 'Preview:' plus the actual body, return JSON with"
        " keys 'subject' and 'body'."
    )
    full_system_prompt = f"{system_prompt}\n\n{base_instructions}" if system_prompt else base_instructions
    class EmailExtraction(BaseModel):
        subject: str
        body: str


    response = client.responses.parse(
        model=model,
        instructions=full_system_prompt,
        input=[
            {"role": "system", "content": base_instructions},
            {"role": "user", "content": newsletter_markdown},
        ],
        text_format=EmailExtraction,
        temperature=0.2,
        max_output_tokens=400,
    )
    parsed = response.output_parsed
    return parsed.subject, parsed.body
