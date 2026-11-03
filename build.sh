#!/usr/bin/env bash
set -o errexit

# نصب کامپایلر Rust برای پکیج‌های نیازمند بیلد (مثل pydantic-core)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
export PATH="$HOME/.cargo/bin:$PATH"

# آپدیت کردن ابزارهای پایتون
pip install --upgrade pip setuptools wheel

# نصب کتابخانه‌های پروژه
pip install -r requirements.txt
