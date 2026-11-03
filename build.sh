#!/usr/bin/env bash
set -o errexit

# اضافه کردن مسیر Rustِ موجود در سرور رندر به متغیرهای محیطی
export PATH="/usr/local/cargo/bin:$PATH"

# آپدیت ابزارهای پایتون
pip install --upgrade pip setuptools wheel

# نصب پکیج‌ها
pip install -r requirements.txt
