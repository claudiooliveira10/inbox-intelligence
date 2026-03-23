# 📬 Inbox Intelligence

<p align="center">
  <img src="https://via.placeholder.com/900x300?text=Inbox+Intelligence" />
</p>

> Transform raw emails into structured, AI-ready knowledge.

---

## ⚡ Overview

Inbox Intelligence is a real-world automation pipeline that converts raw email data into structured, clean, and usable information for AI systems.

Designed for:
- businesses overwhelmed with email
- developers building AI pipelines
- automation-first workflows

---

## 🔥 Problem

Emails are:

- messy  
- unstructured  
- hard to analyze  
- impossible to scale  

👉 Valuable data is hidden inside conversations.

---

## 🚀 Solution

Inbox Intelligence turns email chaos into:

- 🧠 structured intelligence  
- 📊 analyzable data  
- 🤖 AI-ready inputs  

---

## ⚙️ Features

- 📥 Parse emails (Maildir / cPanel / Outlook)
- 🧹 Clean HTML, remove noise & signatures
- 📎 Extract meaningful attachments only
- 🧠 Generate NotebookLM-ready bundles
- 📊 CSV index with metadata
- 🗂 Fully automated pipeline

---

## 🧩 Output

After running, you get:

```bash
output/
├── emails_txt/
├── anexos/
├── notebooklm_bundles/
├── index.csv
└── erros.log

🚀 Usage

python3 converter_emails_notebooklm.py

Or with custom paths:

python3 converter_emails_notebooklm.py \
  --input "./input" \
  --output "./output"
python3 converter_emails_notebooklm.py \
  --input "./input" \
  --output "./output"
