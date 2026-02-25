#!/usr/bin/env python3
"""
Web-based Odoo Implementation Interview - Phased Approach with Voice Support

Features:
- Phase 1: Scoping questions to determine business scope
- Phase 2: Domain expert deep-dives (Sales, Inventory, Finance, etc.)
- Phase 3: Summary with module recommendations
- Visual progress indicator showing where you are
- Voice input (browser microphone) and voice output (Web Speech API)

Run:
    python3 web_interview.py

Then open: http://localhost:5001
"""

import json
import os
import sys
import base64
import tempfile
import threading
import asyncio
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify, Response
import secrets

# Load .env file
_env_path = Path(__file__).resolve().parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.phased_interview_agent import PhasedInterviewAgent, get_total_interview_estimate
from src.schemas.implementation_spec import create_spec_from_interview

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Store agents per session
agents = {}

# Store builds per build_id
builds = {}
builds_lock = threading.Lock()

# Last completed demo result (set by /api/generate-prd, read by /api/demo-result)
last_demo_result = None

# Try to load whisper for server-side transcription
try:
    from src.voice.speech_to_text import SpeechToText
    import numpy as np
    WHISPER_AVAILABLE = True
    whisper_model = None  # Lazy load
except ImportError:
    WHISPER_AVAILABLE = False

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <meta name="theme-color" content="#f5f5f7">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <title>Odoo AI Setup</title>
    <style>
        /* ── Tokens ── */
        :root {
            --bg: #f5f5f7;
            --surface: #ffffff;
            --glass: rgba(255,255,255,0.82);
            --border: rgba(0,0,0,0.07);
            --border-strong: rgba(0,0,0,0.12);
            --text-1: #1d1d1f;
            --text-2: #6e6e73;
            --text-3: #aeaeb2;
            --fill: rgba(0,0,0,0.04);
            --fill-2: rgba(0,0,0,0.07);
            --accent: #0071e3;
            --accent-h: #0077ed;
            --accent-bg: rgba(0,113,227,0.08);
            --green: #34c759;
            --green-bg: rgba(52,199,89,0.09);
            --green-text: #1a7f37;
            --red: #ff3b30;
            --red-bg: rgba(255,59,48,0.09);
            --red-text: #c62828;
            --orange-bg: rgba(255,149,0,0.1);
            --orange-text: #9a4e00;
            --font: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'SF Pro Text', system-ui, sans-serif;
            --mono: 'SF Mono', SFMono-Regular, ui-monospace, Menlo, monospace;
            --ease: cubic-bezier(0.25,0.1,0.25,1);
            --spring: cubic-bezier(0.34,1.56,0.64,1);
            --out: cubic-bezier(0,0,0.2,1);
            --r-sm: 10px; --r: 14px; --r-lg: 20px; --r-xl: 28px;
        }

        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
        html { height: 100%; }
        body {
            font-family: var(--font);
            background: var(--bg);
            min-height: 100%; min-height: 100dvh;
            color: var(--text-1);
            -webkit-font-smoothing: antialiased;
            line-height: 1.47; font-size: 15px;
            overflow-x: hidden;
        }

        /* ── Utility ── */
        .hidden { display: none !important; }

        /* ── Aurora background ── */
        .aurora {
            position: fixed; inset: 0; z-index: 0;
            pointer-events: none; overflow: hidden;
        }
        .aurora::before {
            content: '';
            position: absolute; inset: -20%;
            background:
                radial-gradient(ellipse 70% 55% at 15% 15%, rgba(0,113,227,0.13) 0%, transparent 55%),
                radial-gradient(ellipse 55% 70% at 85% 75%, rgba(52,199,89,0.10) 0%, transparent 55%),
                radial-gradient(ellipse 65% 45% at 55% 95%, rgba(94,92,230,0.08) 0%, transparent 55%);
            animation: auroraMove 14s ease-in-out infinite alternate;
        }
        @keyframes auroraMove {
            0%   { transform: scale(1) rotate(0deg); opacity: .8; }
            100% { transform: scale(1.06) rotate(3deg); opacity: 1; }
        }

        /* ══════════════════════════════
           SETUP SCREEN
        ══════════════════════════════ */
        #setup-form {
            position: relative; z-index: 1;
            min-height: 100vh; min-height: 100dvh;
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            padding: 48px 20px calc(32px + env(safe-area-inset-bottom,0px));
        }

        .setup-brand {
            display: flex; align-items: center; gap: 10px;
            margin-bottom: 36px;
            animation: fadeUp .55s var(--out) both;
        }
        .brand-orb {
            width: 42px; height: 42px; border-radius: 12px;
            background: linear-gradient(135deg, var(--accent) 0%, #5e5ce6 100%);
            display: flex; align-items: center; justify-content: center;
            box-shadow: 0 4px 14px rgba(0,113,227,0.35);
        }
        .brand-orb svg { width: 22px; height: 22px; stroke: #fff; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
        .brand-name { font-size: 17px; font-weight: 700; letter-spacing: -.3px; }

        .setup-headline {
            font-size: clamp(34px, 8vw, 56px);
            font-weight: 700; letter-spacing: -1.8px;
            line-height: 1.03; text-align: center;
            margin-bottom: 14px; max-width: 580px;
            animation: fadeUp .55s var(--out) .07s both;
        }
        .setup-headline em {
            font-style: normal;
            background: linear-gradient(130deg, var(--accent) 0%, #5e5ce6 100%);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            background-clip: text;
        }

        .setup-sub {
            color: var(--text-2); font-size: 17px; text-align: center;
            margin-bottom: 40px; line-height: 1.5; max-width: 380px;
            animation: fadeUp .55s var(--out) .13s both;
        }

        .setup-card {
            width: 100%; max-width: 420px;
            background: var(--glass);
            backdrop-filter: blur(48px); -webkit-backdrop-filter: blur(48px);
            border: .5px solid rgba(255,255,255,.75);
            border-radius: var(--r-xl);
            box-shadow: 0 8px 48px rgba(0,0,0,.09), 0 1px 0 rgba(255,255,255,.9) inset;
            padding: 28px;
            animation: fadeUp .55s var(--out) .19s both;
        }

        @keyframes fadeUp {
            from { opacity: 0; transform: translateY(22px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        .form-stack { display: flex; flex-direction: column; gap: 16px; }

        .field { display: flex; flex-direction: column; gap: 6px; }
        .field label { font-size: 13px; font-weight: 600; color: var(--text-2); }

        .field input, .field select {
            width: 100%; padding: 13px 16px;
            border: 1px solid var(--border-strong); border-radius: var(--r);
            font-size: 16px; font-family: var(--font);
            background: var(--surface); color: var(--text-1);
            transition: border-color .15s, box-shadow .15s;
            appearance: none; -webkit-appearance: none;
        }
        .field select {
            background-image: url("data:image/svg+xml,%3Csvg width='12' height='8' viewBox='0 0 12 8' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1.5L6 6.5L11 1.5' stroke='%236e6e73' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
            background-repeat: no-repeat; background-position: right 16px center;
            padding-right: 40px;
        }
        .field input:focus, .field select:focus {
            outline: none; border-color: var(--accent);
            box-shadow: 0 0 0 4px rgba(0,113,227,.10);
        }
        .field input::placeholder { color: var(--text-3); }

        /* Voice row */
        .voice-row {
            display: flex; align-items: center; justify-content: space-between;
            padding: 8px 0 4px;
        }
        .voice-row-label {
            display: flex; align-items: center; gap: 8px;
            font-size: 14px; font-weight: 500; color: var(--text-2);
        }
        .voice-row-label svg { width: 16px; height: 16px; stroke: var(--text-2); fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }

        /* Toggle */
        .toggle { position: relative; width: 44px; height: 26px; flex-shrink: 0; }
        .toggle input { opacity: 0; width: 0; height: 0; position: absolute; }
        .toggle-track {
            position: absolute; inset: 0;
            background: var(--text-3); border-radius: 26px;
            cursor: pointer; transition: background .2s var(--ease);
        }
        .toggle-track::before {
            content: ''; position: absolute;
            width: 20px; height: 20px; left: 3px; top: 3px;
            background: #fff; border-radius: 50%;
            transition: transform .25s var(--spring);
            box-shadow: 0 1px 4px rgba(0,0,0,.18);
        }
        .toggle input:checked + .toggle-track { background: var(--green); }
        .toggle input:checked + .toggle-track::before { transform: translateX(18px); }

        /* Small toggle variant */
        .toggle-sm { width: 36px; height: 22px; }
        .toggle-sm .toggle-track::before { width: 16px; height: 16px; left: 3px; top: 3px; }
        .toggle-sm input:checked + .toggle-track::before { transform: translateX(14px); }

        /* CTA button */
        .btn-cta {
            width: 100%; padding: 15px;
            background: var(--accent); color: #fff;
            border: none; border-radius: var(--r);
            font-size: 16px; font-weight: 600; font-family: var(--font);
            cursor: pointer; transition: all .15s var(--ease);
            display: flex; align-items: center; justify-content: center; gap: 8px;
        }
        .btn-cta:hover { background: var(--accent-h); transform: translateY(-1px); box-shadow: 0 6px 22px rgba(0,113,227,.28); }
        .btn-cta:active { transform: scale(.97) translateY(0); box-shadow: none; }
        .btn-cta:disabled { opacity: .4; cursor: not-allowed; transform: none; box-shadow: none; }
        .btn-cta svg { width: 16px; height: 16px; stroke: #fff; fill: none; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }

        /* ══════════════════════════════
           LOADING SCREEN
        ══════════════════════════════ */
        #loading {
            position: fixed; inset: 0; z-index: 200;
            display: flex; flex-direction: column;
            align-items: center; justify-content: center;
            background: var(--bg); gap: 22px;
        }
        .loader-orb {
            width: 60px; height: 60px; border-radius: 50%;
            background: linear-gradient(135deg, var(--accent), #5e5ce6);
            animation: orbPop 1.4s ease-in-out infinite;
            box-shadow: 0 0 36px rgba(0,113,227,.28);
        }
        @keyframes orbPop {
            0%,100% { transform: scale(.88); opacity: .75; }
            50%      { transform: scale(1.12); opacity: 1; }
        }
        .loader-text { font-size: 16px; font-weight: 500; color: var(--text-2); }

        /* ══════════════════════════════
           CHAT SCREEN
        ══════════════════════════════ */
        #chat-container { display: none; }
        #chat-container.active {
            position: fixed; inset: 0; z-index: 10;
            display: flex; flex-direction: column;
            background: var(--bg);
            animation: screenIn .4s var(--out) both;
        }
        @keyframes screenIn {
            from { opacity: 0; transform: translateY(14px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        /* Header */
        .chat-hd {
            flex-shrink: 0;
            background: var(--glass);
            backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
            border-bottom: .5px solid var(--border);
            padding-top: env(safe-area-inset-top, 0px);
        }

        /* Top progress line */
        .hd-progress-track {
            height: 2px; background: var(--border); overflow: hidden;
        }
        #progress-bar {
            height: 100%;
            background: linear-gradient(90deg, var(--accent), #5e5ce6);
            width: 0%; transition: width .7s var(--out); border-radius: 2px;
        }

        /* Header row */
        .hd-row {
            padding: 13px 18px;
            display: flex; align-items: center; gap: 10px;
        }

        .hd-phase {
            flex: 1; display: flex; align-items: center;
            gap: 10px; min-width: 0;
        }

        /* Phase dots */
        .phase-dots { display: flex; gap: 4px; align-items: center; flex-shrink: 0; }
        .pdot {
            width: 6px; height: 6px; border-radius: 50%;
            background: var(--border-strong);
            transition: all .3s var(--ease);
        }
        .pdot.active { background: var(--accent); width: 18px; border-radius: 3px; }
        .pdot.done   { background: var(--green); }

        .hd-phase-label {
            font-size: 13px; font-weight: 600; color: var(--text-1);
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }

        .hd-pct {
            font-size: 12px; font-weight: 700; color: var(--accent);
            background: var(--accent-bg); padding: 3px 9px;
            border-radius: 100px; white-space: nowrap; flex-shrink: 0;
            font-variant-numeric: tabular-nums;
        }

        .hd-voice {
            display: flex; align-items: center; gap: 6px;
            font-size: 11px; color: var(--text-3); flex-shrink: 0;
        }

        /* Domain pills row */
        .domain-pills-row {
            padding: 0 18px 11px;
            display: flex; flex-wrap: nowrap; gap: 6px;
            overflow-x: auto; scrollbar-width: none; -ms-overflow-style: none;
        }
        .domain-pills-row::-webkit-scrollbar { display: none; }

        .domain-pill {
            padding: 4px 10px; border-radius: 100px;
            font-size: 12px; font-weight: 500;
            white-space: nowrap; flex-shrink: 0;
            transition: all .2s var(--ease);
        }
        .domain-pill.active    { background: var(--accent); color: #fff; }
        .domain-pill.completed { background: var(--green-bg); color: var(--green-text); }
        .domain-pill.pending   { background: var(--fill); color: var(--text-3); }

        /* Voice status bar */
        .voice-status {
            display: none; align-items: center; gap: 8px;
            padding: 8px 18px; font-size: 13px; font-weight: 500;
            border-top: .5px solid var(--border);
        }
        .voice-status.active    { display: flex; background: var(--accent-bg); color: var(--accent); }
        .voice-status.listening { display: flex; background: var(--red-bg); color: var(--red-text); }
        .voice-status.speaking  { display: flex; background: var(--green-bg); color: var(--green-text); }
        .vdot {
            width: 6px; height: 6px; border-radius: 50%; background: currentColor;
            animation: vdotPulse 1s ease-in-out infinite; flex-shrink: 0;
        }
        @keyframes vdotPulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.35;transform:scale(.6)} }

        /* Messages */
        .chat-messages {
            flex: 1; overflow-y: auto; padding: 20px 16px 10px;
            scroll-behavior: smooth; overscroll-behavior: contain;
            -webkit-overflow-scrolling: touch;
        }

        .message {
            display: flex; gap: 9px; margin-bottom: 12px;
            animation: msgIn .28s var(--out) both;
        }
        @keyframes msgIn { from{opacity:0;transform:translateY(7px)} to{opacity:1;transform:translateY(0)} }
        .message.bot  { flex-direction: row; }
        .message.user { flex-direction: row-reverse; }
        .message.system { justify-content: center; }

        .message-avatar {
            width: 28px; height: 28px; border-radius: 50%;
            display: flex; align-items: center; justify-content: center;
            flex-shrink: 0; margin-top: 2px;
        }
        .message.bot .message-avatar  { background: var(--accent-bg); }
        .message.user .message-avatar { background: var(--fill-2); }
        .message-avatar svg { width: 13px; height: 13px; fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
        .message.bot .message-avatar svg  { stroke: var(--accent); }
        .message.user .message-avatar svg { stroke: var(--text-2); }

        .message-content {
            max-width: 78%; padding: 10px 14px;
            border-radius: 18px; line-height: 1.5; font-size: 15px;
        }
        .message.bot .message-content {
            background: var(--surface); color: var(--text-1);
            border-bottom-left-radius: 5px;
            box-shadow: 0 1px 4px rgba(0,0,0,.055);
        }
        .message.user .message-content {
            background: var(--accent); color: #fff;
            border-bottom-right-radius: 5px;
        }
        .message.system .message-content {
            background: var(--orange-bg); color: var(--orange-text);
            font-size: 13px; max-width: 88%; text-align: center;
            border-radius: var(--r); padding: 8px 14px;
        }
        .expert-intro { background: var(--accent-bg) !important; color: var(--accent) !important; }

        /* Typing indicator */
        .typing-indicator { display: flex; gap: 5px; align-items: center; padding: 5px 2px; }
        .typing-indicator span {
            width: 6px; height: 6px; border-radius: 50%;
            background: var(--text-3); animation: tdot 1.2s infinite ease-in-out;
        }
        .typing-indicator span:nth-child(1) { animation-delay: -.32s; }
        .typing-indicator span:nth-child(2) { animation-delay: -.16s; }
        @keyframes tdot { 0%,80%,100%{transform:scale(.6);opacity:.4} 40%{transform:scale(1);opacity:1} }

        /* Input area */
        .chat-input-wrapper {
            flex-shrink: 0;
            background: var(--glass);
            backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
            border-top: .5px solid var(--border);
            padding: 10px 16px calc(10px + env(safe-area-inset-bottom,0px));
        }

        .input-pill {
            display: flex; align-items: center; gap: 8px;
            background: var(--fill); border: 1px solid var(--border-strong);
            border-radius: 100px; padding: 6px 6px 6px 18px;
            transition: border-color .15s, box-shadow .15s, background .15s;
        }
        .input-pill:focus-within {
            border-color: var(--accent);
            box-shadow: 0 0 0 4px rgba(0,113,227,.09);
            background: var(--surface);
        }

        .chat-input {
            flex: 1; background: transparent; border: none; outline: none;
            font-family: var(--font); font-size: 16px; color: var(--text-1);
            line-height: 1.4; padding: 4px 0;
        }
        .chat-input::placeholder { color: var(--text-3); }

        .mic-btn {
            width: 44px; height: 44px; border-radius: 50%; border: none;
            background: transparent; color: var(--text-2); cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            transition: all .15s var(--ease); flex-shrink: 0;
        }
        .mic-btn:hover { background: var(--fill-2); color: var(--text-1); }
        .mic-btn svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
        .mic-btn.recording {
            background: var(--red); color: #fff;
            animation: micRing 1.1s ease-in-out infinite;
        }
        @keyframes micRing {
            0%,100% { box-shadow: 0 0 0 0 rgba(255,59,48,.45); }
            55%      { box-shadow: 0 0 0 9px rgba(255,59,48,0); }
        }

        .send-btn {
            width: 44px; height: 44px; border-radius: 50%; border: none;
            background: var(--accent); cursor: pointer;
            display: flex; align-items: center; justify-content: center;
            transition: all .15s var(--ease); flex-shrink: 0;
        }
        .send-btn:hover { background: var(--accent-h); transform: scale(1.06); }
        .send-btn:active { transform: scale(.93); }
        .send-btn svg { width: 15px; height: 15px; stroke: #fff; fill: none; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }

        .action-row { display: flex; gap: 4px; margin-top: 8px; padding: 0 6px; }
        .btn-ghost {
            padding: 7px 16px; background: transparent; border: none;
            color: var(--text-2); font-size: 13px; font-weight: 500;
            font-family: var(--font); cursor: pointer; border-radius: 100px;
            transition: all .15s var(--ease);
        }
        .btn-ghost:hover { background: var(--fill-2); color: var(--text-1); }

        /* ══════════════════════════════
           SUMMARY SCREEN
        ══════════════════════════════ */
        #summary { display: none; }
        #summary.active {
            position: fixed; inset: 0; z-index: 20;
            display: flex; flex-direction: column;
            background: var(--bg);
            animation: screenIn .4s var(--out) both;
        }

        .sum-hd {
            flex-shrink: 0;
            background: var(--glass);
            backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
            border-bottom: .5px solid var(--border);
            padding: calc(env(safe-area-inset-top,0px) + 18px) 20px 18px;
        }
        .sum-hd h2 { font-size: 21px; font-weight: 700; letter-spacing: -.45px; }
        .sum-hd p  { font-size: 13px; color: var(--text-2); margin-top: 3px; }

        .sum-body {
            flex: 1; overflow-y: auto;
            padding: 18px 16px calc(18px + env(safe-area-inset-bottom,0px));
            -webkit-overflow-scrolling: touch;
        }

        .sum-section {
            background: var(--surface); border-radius: var(--r-lg);
            padding: 18px 20px; margin-bottom: 10px;
            box-shadow: 0 1px 4px rgba(0,0,0,.05);
        }
        .sum-section h4 {
            font-size: 11px; font-weight: 700; color: var(--text-3);
            text-transform: uppercase; letter-spacing: .8px; margin-bottom: 10px;
        }
        .sum-section p { font-size: 15px; color: var(--text-1); line-height: 1.5; margin-bottom: 4px; }
        .sum-section p:last-child { margin-bottom: 0; }

        .module-grid { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
        .module-tag {
            background: var(--green-bg); color: var(--green-text);
            padding: 4px 11px; border-radius: 100px;
            font-size: 12px; font-weight: 600;
        }

        /* Summary actions */
        .sum-actions { display: flex; flex-direction: column; gap: 10px; padding: 2px 0 6px; }
        .deploy-row { display: flex; gap: 10px; align-items: center; }
        .deploy-select {
            flex: 1; padding: 13px 16px;
            border: .5px solid var(--border-strong); border-radius: var(--r);
            font-size: 15px; font-family: var(--font);
            background: var(--surface); color: var(--text-1);
            appearance: none; -webkit-appearance: none;
            background-image: url("data:image/svg+xml,%3Csvg width='12' height='8' viewBox='0 0 12 8' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1.5L6 6.5L11 1.5' stroke='%236e6e73' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
            background-repeat: no-repeat; background-position: right 14px center;
            padding-right: 36px;
        }

        .btn-sum {
            padding: 14px 20px; border-radius: var(--r);
            font-size: 15px; font-weight: 600; font-family: var(--font);
            cursor: pointer; border: none; transition: all .15s var(--ease);
            text-align: center; letter-spacing: -.1px;
        }
        .btn-sum:active { transform: scale(.97); }
        .btn-sum.primary  { background: var(--accent); color: #fff; }
        .btn-sum.primary:hover { background: var(--accent-h); }
        .btn-sum.success  { background: var(--green-text); color: #fff; }
        .btn-sum.success:hover { opacity: .9; }
        .btn-sum.muted    { background: var(--fill); color: var(--text-1); border: .5px solid var(--border-strong); }
        .btn-sum.muted:hover { background: var(--fill-2); }
        .btn-sum:disabled { opacity: .4; cursor: not-allowed; transform: none; }

        /* PRD */
        .prd-container {
            background: var(--surface); border-radius: var(--r-lg);
            padding: 20px; margin-bottom: 10px;
            font-size: 14px; line-height: 1.65;
            box-shadow: 0 1px 4px rgba(0,0,0,.05);
        }
        .prd-container h1 {
            font-size: 19px; font-weight: 700; letter-spacing: -.4px;
            border-bottom: .5px solid var(--border); padding-bottom: 12px; margin-bottom: 20px;
        }
        .prd-container h2 { font-size: 15px; font-weight: 700; margin: 24px 0 10px; letter-spacing: -.2px; }
        .prd-container h3 { font-size: 13px; font-weight: 600; color: var(--text-2); margin: 18px 0 6px; }
        .prd-container p { margin-bottom: 10px; }
        .prd-container table { width: 100%; border-collapse: collapse; margin: 14px 0; font-size: 13px; }
        .prd-container th, .prd-container td { border: .5px solid var(--border-strong); padding: 8px 12px; text-align: left; }
        .prd-container th { background: var(--fill); font-weight: 700; font-size: 11px; text-transform: uppercase; letter-spacing: .4px; color: var(--text-2); }
        .prd-container tr:nth-child(even) { background: var(--fill); }
        .prd-container code { background: var(--fill); padding: 1px 6px; border-radius: 5px; font-size: 12px; font-family: var(--mono); color: var(--accent); }
        .prd-container pre { background: #1c1c1e; border-radius: var(--r-sm); padding: 14px; overflow-x: auto; font-size: 12px; font-family: var(--mono); line-height: 1.5; color: #e5e5ea; margin: 12px 0; }
        .prd-container pre code { background: none; padding: 0; color: inherit; }
        .prd-container ul, .prd-container ol { padding-left: 20px; margin: 8px 0; }
        .prd-container li { margin-bottom: 4px; }

        .prd-loading {
            text-align: center; padding: 40px 20px;
            background: var(--surface); border-radius: var(--r-lg);
            margin-bottom: 10px; color: var(--text-2); font-size: 14px;
        }
        .prd-spinner {
            width: 24px; height: 24px; border: 2px solid var(--border-strong);
            border-top-color: var(--accent); border-radius: 50%;
            animation: spin .7s linear infinite; margin: 0 auto 14px;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* Deploy panel */
        .deploy-panel {
            display: none; background: var(--surface);
            border-radius: var(--r-lg); overflow: hidden;
            margin-bottom: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.05);
        }
        .deploy-panel.active { display: block; }
        .deploy-panel-header {
            padding: 14px 18px; font-weight: 700; font-size: 14px;
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: .5px solid var(--border);
        }
        .deploy-progress-bar { background: var(--border); height: 3px; overflow: hidden; }
        .deploy-progress-fill {
            background: linear-gradient(90deg, var(--green), #30d158);
            height: 100%; transition: width .6s var(--out); width: 0%;
        }
        .deploy-tasks { padding: 0 18px; max-height: 220px; overflow-y: auto; }
        .deploy-task { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-bottom: .5px solid var(--border); font-size: 13px; }
        .deploy-task-icon { width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; }
        .deploy-task-icon svg { width: 14px; height: 14px; }
        .deploy-task-name { flex: 1; color: var(--text-1); }
        .deploy-task-progress { color: var(--text-3); font-size: 12px; min-width: 36px; text-align: right; font-variant-numeric: tabular-nums; }
        .deploy-log {
            background: #1c1c1e; color: #98989d; font-family: var(--mono);
            font-size: 11.5px; line-height: 1.6; padding: 14px;
            margin: 10px 18px; border-radius: var(--r-sm);
            max-height: 160px; overflow-y: auto; white-space: pre-wrap; overflow-wrap: break-word;
        }
        .deploy-success {
            display: none; background: var(--green-bg); border-radius: var(--r-sm);
            padding: 14px 18px; margin: 10px 18px 18px; color: var(--green-text); font-size: 14px;
        }
        .deploy-success a { color: var(--green-text); font-weight: 700; }
        .deploy-error {
            display: none; background: var(--red-bg); border-radius: var(--r-sm);
            padding: 14px 18px; margin: 10px 18px 18px; color: var(--red-text); font-size: 14px;
        }
        .deploy-footer { padding: 10px 18px; display: flex; gap: 8px; }
        .btn-stop {
            background: var(--red-bg); color: var(--red-text); border: none;
            padding: 8px 16px; border-radius: 100px;
            font-size: 13px; font-weight: 600; font-family: var(--font);
            cursor: pointer; transition: opacity .15s;
        }
        .btn-stop:hover { opacity: .8; }
        .btn-stop:disabled { opacity: .4; cursor: not-allowed; }

        /* ── Mobile ── */
        @media (max-width: 480px) {
            .setup-headline { font-size: 33px; letter-spacing: -1.2px; }
            .setup-sub { font-size: 15px; }
            .hd-row { padding: 11px 14px; }
            .domain-pills-row { padding: 0 14px 10px; }
            .chat-messages { padding: 16px 12px 8px; }
            .message-content { font-size: 14px; max-width: 84%; }
            .chat-input-wrapper { padding: 8px 12px calc(8px + env(safe-area-inset-bottom,0px)); }
            .sum-body { padding: 14px 12px calc(14px + env(safe-area-inset-bottom,0px)); }
            .sum-section { padding: 16px; }
            .prd-container { padding: 16px; }
        }
        @media (max-width: 360px) {
            .setup-headline { font-size: 28px; }
            .btn-cta { font-size: 15px; }
        }
    </style>
</head>
<body>

<!-- Aurora background (always behind everything) -->
<div class="aurora"></div>

<!-- ══════════════════════════════
     SETUP SCREEN
══════════════════════════════ -->
<div id="setup-form">
    <div class="setup-brand">
        <div class="brand-orb">
            <svg viewBox="0 0 24 24"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
        </div>
        <span class="brand-name">Odoo AI</span>
    </div>

    <h1 class="setup-headline">ERP discovery,<br><em>reimagined</em></h1>
    <p class="setup-sub">AI-guided requirements gathering for your Odoo implementation. Voice-first, done in minutes.</p>

    <div class="setup-card">
        <div class="form-stack">
            <div class="field">
                <label for="client-name">Company name</label>
                <input type="text" id="client-name" placeholder="e.g. Acme Corporation" autocomplete="organization" required>
            </div>
            <div class="field">
                <label for="industry">Industry</label>
                <select id="industry">
                    <option value="E-commerce">E-commerce / Online Retail</option>
                    <option value="Manufacturing">Manufacturing</option>
                    <option value="Retail">Retail / Brick &amp; Mortar</option>
                    <option value="Services">Professional Services</option>
                    <option value="Distribution">Distribution / Wholesale</option>
                    <option value="Healthcare">Healthcare</option>
                    <option value="Construction">Construction</option>
                    <option value="Food &amp; Beverage">Food &amp; Beverage</option>
                    <option value="Technology">Technology / Software</option>
                    <option value="Other">Other</option>
                </select>
            </div>
            <div class="voice-row">
                <span class="voice-row-label">
                    <svg viewBox="0 0 24 24"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg>
                    Enable voice
                </span>
                <label class="toggle">
                    <input type="checkbox" id="voice-enabled" checked>
                    <span class="toggle-track"></span>
                </label>
            </div>
            <button class="btn-cta" onclick="startInterview()">
                Start interview
                <svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </button>
        </div>
    </div>
</div>

<!-- ══════════════════════════════
     LOADING
══════════════════════════════ -->
<div id="loading" class="hidden">
    <div class="loader-orb"></div>
    <p class="loader-text">Setting up your interview&hellip;</p>
</div>

<!-- ══════════════════════════════
     CHAT SCREEN
══════════════════════════════ -->
<div id="chat-container">
    <div class="chat-hd">
        <div class="hd-progress-track">
            <div id="progress-bar"></div>
        </div>
        <div class="hd-row">
            <div class="hd-phase">
                <div class="phase-dots">
                    <div class="pdot" id="phase-scoping"></div>
                    <div class="pdot" id="phase-domains"></div>
                    <div class="pdot" id="phase-summary"></div>
                </div>
                <span class="hd-phase-label" id="current-phase">Scoping</span>
            </div>
            <span class="hd-pct" id="progress-percent">0%</span>
            <div class="hd-voice">
                <span>Voice</span>
                <label class="toggle toggle-sm">
                    <input type="checkbox" id="voice-toggle-chat" checked>
                    <span class="toggle-track"></span>
                </label>
            </div>
        </div>
        <div class="domain-pills-row" id="domain-pills"></div>
        <div class="voice-status" id="voice-status">
            <div class="vdot"></div>
            <span id="voice-status-text">Listening&hellip;</span>
        </div>
    </div>

    <div class="chat-messages" id="chat-messages"></div>

    <div class="chat-input-wrapper">
        <div class="input-pill">
            <input class="chat-input" type="text" id="user-input"
                   placeholder="Type your answer&hellip;"
                   onkeypress="handleKeyPress(event)"
                   autocomplete="off">
            <button class="mic-btn" id="mic-btn" onclick="toggleRecording()" aria-label="Toggle voice recording">
                <svg viewBox="0 0 24 24"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="22"/></svg>
            </button>
            <button class="send-btn" onclick="sendMessage()" aria-label="Send message">
                <svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
            </button>
        </div>
        <div class="action-row">
            <button class="btn-ghost" onclick="skipQuestion()">Skip</button>
            <button class="btn-ghost" onclick="endInterview()">End interview</button>
        </div>
    </div>
</div>

<!-- ══════════════════════════════
     SUMMARY SCREEN
══════════════════════════════ -->
<div id="summary">
    <div class="sum-hd">
        <h2>Interview complete</h2>
        <p>Your Odoo implementation requirements are ready.</p>
    </div>
    <div class="sum-body">
        <div id="summary-content"></div>
        <div id="prd-content"></div>

        <div class="sum-actions">
            <div class="deploy-row" id="deploy-target-row" style="display:none;">
                <label id="deploy-target-label" style="font-size:14px;font-weight:600;color:var(--text-2);white-space:nowrap;">Deploy to</label>
                <select id="deploy-target" class="deploy-select" onchange="updateDeployButton()">
                    <option value="docker">Local Docker</option>
                    <option value="railway" selected>Railway Cloud</option>
                </select>
            </div>
            <button class="btn-sum success" id="btn-deploy" onclick="startDeploy()" style="display:none;">Deploy to Odoo</button>
            <button class="btn-sum primary" id="btn-download-md" onclick="downloadPrdMarkdown()" style="display:none;">Download PRD (Markdown)</button>
            <button class="btn-sum muted" id="btn-download-json" onclick="downloadPrdJson()" style="display:none;">Download PRD (JSON)</button>
            <button class="btn-sum muted" onclick="startOver()">Start new interview</button>
        </div>

        <div id="deploy-panel" class="deploy-panel">
            <div class="deploy-panel-header">
                <span id="deploy-status-text">Deploying to Odoo&hellip;</span>
                <span id="deploy-percent">0%</span>
            </div>
            <div class="deploy-progress-bar" role="progressbar" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100">
                <div class="deploy-progress-fill" id="deploy-progress-fill"></div>
            </div>
            <div class="deploy-tasks" id="deploy-tasks"></div>
            <div class="deploy-log" id="deploy-log" role="log" aria-label="Deployment logs"></div>
            <div class="deploy-success" id="deploy-success" aria-live="polite"></div>
            <div class="deploy-error" id="deploy-error" aria-live="assertive"></div>
            <div class="deploy-footer">
                <button class="btn-stop" id="btn-stop-deploy" onclick="stopDeploy()" aria-label="Stop deployment">Stop</button>
            </div>
        </div>
    </div>
</div>

<script>
    let sessionId = null;
    let interviewData = null;
    let currentQuestion = null;

    // Voice state
    let isRecording = false;
    let mediaRecorder = null;
    let audioChunks = [];
    let voiceEnabled = true;
    let speechSynthesis = window.speechSynthesis;
    let currentAudio = null;
    let recognition = null;

    const hasMediaRecorder = !!window.MediaRecorder;
    const hasSpeechSynthesis = !!window.speechSynthesis;
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const hasWebSpeech = !!SpeechRecognition;

    // iOS/Safari audio unlock — must happen inside a user gesture
    let _audioUnlocked = false;
    function _unlockAudio() {
        if (_audioUnlocked) return;
        _audioUnlocked = true;
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const buf = ctx.createBuffer(1, 1, 22050);
            const src = ctx.createBufferSource();
            src.buffer = buf; src.connect(ctx.destination); src.start(0);
            ctx.resume();
        } catch(e) {}
    }
    document.addEventListener('click',      _unlockAudio, { once: true, passive: true });
    document.addEventListener('touchstart', _unlockAudio, { once: true, passive: true });

    // Sync setup toggle → voiceEnabled state
    document.getElementById('voice-enabled').addEventListener('change', (e) => {
        voiceEnabled = e.target.checked;
        const chatToggle = document.getElementById('voice-toggle-chat');
        if (chatToggle) chatToggle.checked = voiceEnabled;
        if (!voiceEnabled) { stopRecording(); stopSpeaking(); }
    });

    // Chat header toggle syncs back
    document.getElementById('voice-toggle-chat').addEventListener('change', (e) => {
        voiceEnabled = e.target.checked;
        document.getElementById('voice-enabled').checked = voiceEnabled;
        if (!voiceEnabled) { stopRecording(); stopSpeaking(); }
    });

    function stopSpeaking() {
        if (currentAudio) { currentAudio.pause(); currentAudio.currentTime = 0; currentAudio = null; }
        speechSynthesis.cancel();
        hideVoiceStatus();
    }

    // Check for ElevenLabs
    let useElevenLabs = false;
    fetch('/api/tts/status')
        .then(r => r.json())
        .then(data => { useElevenLabs = data.elevenlabs; })
        .catch(() => {});

    function speak(text) {
        stopSpeaking();
        if (!voiceEnabled) return Promise.resolve();
        if (useElevenLabs) return speakElevenLabs(text);
        if (!hasSpeechSynthesis) return Promise.resolve();
        return speakBrowser(text);
    }

    function speakElevenLabs(text) {
        setVoiceStatus('speaking', 'Speaking...');
        return fetch('/api/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        })
        .then(response => {
            if (!response.ok || response.headers.get('content-type')?.includes('json')) return speakBrowser(text);
            return response.blob();
        })
        .then(blob => {
            if (!blob || blob.type?.includes('json')) { hideVoiceStatus(); return speakBrowser(text); }
            return new Promise((resolve) => {
                const url = URL.createObjectURL(blob);
                const audio = new Audio(url);
                currentAudio = audio;
                audio.onended = () => { URL.revokeObjectURL(url); currentAudio = null; hideVoiceStatus(); resolve(); };
                audio.onerror = () => { URL.revokeObjectURL(url); currentAudio = null; hideVoiceStatus(); resolve(); };
                audio.play().catch(() => { currentAudio = null; hideVoiceStatus(); resolve(); });
            });
        })
        .catch(() => { hideVoiceStatus(); return speakBrowser(text); });
    }

    function speakBrowser(text) {
        if (!hasSpeechSynthesis) return Promise.resolve();
        return new Promise((resolve) => {
            speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.rate = 1.0; utterance.pitch = 1.0;
            const voices = speechSynthesis.getVoices();
            const englishVoice = voices.find(v => v.lang.startsWith('en') && v.name.includes('Samantha')) ||
                                 voices.find(v => v.lang.startsWith('en-US')) ||
                                 voices.find(v => v.lang.startsWith('en'));
            if (englishVoice) utterance.voice = englishVoice;
            setVoiceStatus('speaking', 'Speaking...');
            utterance.onend = () => { hideVoiceStatus(); resolve(); };
            utterance.onerror = () => { hideVoiceStatus(); resolve(); };
            speechSynthesis.speak(utterance);
        });
    }

    function startRecording() {
        stopSpeaking();
        _unlockAudio();
        if (hasWebSpeech) {
            _startWebSpeech();
        } else if (hasMediaRecorder) {
            _startMediaRecorder();
        } else {
            addMessage('system', 'Voice input not available in this browser — please type your answer.');
        }
    }

    function _startWebSpeech() {
        try {
            recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.interimResults = true;
            recognition.lang = 'en-US';
            recognition.maxAlternatives = 1;

            recognition.onstart = () => {
                isRecording = true;
                document.getElementById('mic-btn').classList.add('recording');
                setVoiceStatus('listening', 'Listening… tap mic to stop');
            };

            // Show live interim transcript in the input box
            recognition.onresult = (event) => {
                let interim = '', final = '';
                for (let i = event.resultIndex; i < event.results.length; i++) {
                    (event.results[i].isFinal ? (final += event.results[i][0].transcript)
                                              : (interim += event.results[i][0].transcript));
                }
                document.getElementById('user-input').value = final || interim;
            };

            recognition.onend = () => {
                isRecording = false;
                recognition = null;
                document.getElementById('mic-btn').classList.remove('recording');
                hideVoiceStatus();
                const text = document.getElementById('user-input').value.trim();
                if (text) sendMessage();
            };

            recognition.onerror = (event) => {
                isRecording = false;
                recognition = null;
                document.getElementById('mic-btn').classList.remove('recording');
                hideVoiceStatus();
                if (event.error === 'not-allowed') {
                    addMessage('system', 'Microphone access denied — please enable it in browser settings.');
                } else if (event.error !== 'no-speech') {
                    addMessage('system', "Couldn't catch that. Please try again or type your answer.");
                }
            };

            recognition.start();
        } catch (err) {
            console.error('Web Speech error:', err);
            // Fallback to MediaRecorder if Web Speech fails to start
            _startMediaRecorder();
        }
    }

    async function _startMediaRecorder() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            // Pick best supported MIME type (webm for Chrome, mp4 for iOS Safari)
            const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm'
                           : MediaRecorder.isTypeSupported('audio/mp4')  ? 'audio/mp4'
                           : '';
            mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
            audioChunks = [];
            mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
            mediaRecorder.onstop = async () => {
                const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
                stream.getTracks().forEach(track => track.stop());
                await _sendAudioToServer(audioBlob);
            };
            mediaRecorder.start();
            isRecording = true;
            document.getElementById('mic-btn').classList.add('recording');
            setVoiceStatus('listening', 'Listening… tap mic to stop');
        } catch (err) {
            console.error('Microphone error:', err);
            addMessage('system', 'Could not access microphone. Please check permissions or type your answer.');
        }
    }

    function stopRecording() {
        if (hasWebSpeech && recognition) {
            recognition.stop(); // triggers onend → sendMessage
        } else if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            isRecording = false;
            document.getElementById('mic-btn').classList.remove('recording');
            setVoiceStatus('active', 'Processing…');
        }
    }

    function toggleRecording() {
        if (isRecording) stopRecording(); else startRecording();
    }

    async function _sendAudioToServer(audioBlob) {
        try {
            const reader = new FileReader();
            reader.readAsDataURL(audioBlob);
            reader.onloadend = async () => {
                const base64Audio = reader.result.split(',')[1];
                const response = await fetch('/api/transcribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ audio: base64Audio })
                });
                const data = await response.json();
                hideVoiceStatus();
                if (data.text && data.text.trim()) {
                    document.getElementById('user-input').value = data.text;
                    sendMessage();
                } else {
                    addMessage('system', "Couldn't understand that. Please try again or type your answer.");
                }
            };
        } catch (err) {
            console.error('Transcription error:', err);
            hideVoiceStatus();
            addMessage('system', 'Error processing voice. Please type your answer.');
        }
    }

    function setVoiceStatus(type, text) {
        const el = document.getElementById('voice-status');
        const tx = document.getElementById('voice-status-text');
        el.className = 'voice-status active ' + type;
        tx.textContent = text;
    }
    function hideVoiceStatus() {
        document.getElementById('voice-status').className = 'voice-status';
    }

    async function startInterview() {
        const clientName = document.getElementById('client-name').value.trim();
        const industry = document.getElementById('industry').value;
        if (!clientName) { alert('Please enter a company name'); return; }

        document.getElementById('setup-form').classList.add('hidden');
        document.getElementById('loading').classList.remove('hidden');

        try {
            const response = await fetch('/api/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ client_name: clientName, industry: industry })
            });
            const data = await response.json();
            sessionId = data.session_id;

            document.getElementById('loading').classList.add('hidden');
            document.getElementById('chat-container').classList.add('active');

            const welcomeMsg = `Welcome! I'm here to help gather requirements for ${clientName}'s Odoo implementation.`;
            addMessage('bot', welcomeMsg);
            await speak(welcomeMsg);

            const phaseMsg = "We'll go through this in phases: first, quick scoping questions, then detailed domain deep-dives, and finally your module recommendations.";
            addMessage('bot', phaseMsg);
            await speak(phaseMsg);

            await getNextQuestion();
        } catch (error) {
            console.error('Error:', error);
            alert('Failed to start interview. Make sure the server is running.');
            document.getElementById('loading').classList.add('hidden');
            document.getElementById('setup-form').classList.remove('hidden');
        }
    }

    async function getNextQuestion() {
        try {
            const response = await fetch(`/api/question?session_id=${sessionId}`);
            const data = await response.json();
            if (data.complete) { showSummary(data.summary); return; }

            currentQuestion = data;
            if (data.expert_intro) { addMessage('bot', data.expert_intro, 'expert-intro'); await speak(data.expert_intro); }

            let displayText = data.question;
            if (data.context && data.phase !== 'scoping') {
                displayText += `<br><small style="color:var(--text-3);font-size:13px;">${data.context}</small>`;
            }
            addMessage('bot', displayText);
            await speak(data.question);
            updateProgress(data.progress);

            if (voiceEnabled && (hasWebSpeech || hasMediaRecorder)) {
                setTimeout(() => { if (!isRecording) startRecording(); }, 150);
            }
        } catch (error) {
            console.error('Error:', error);
            addMessage('system', 'Sorry, there was an error getting the next question.');
        }
    }

    async function sendMessage() {
        const input = document.getElementById('user-input');
        const message = input.value.trim();
        if (!message || !currentQuestion) return;

        stopSpeaking();
        if (isRecording) { mediaRecorder.stop(); isRecording = false; document.getElementById('mic-btn').classList.remove('recording'); }

        input.value = '';
        addMessage('user', message);
        showTyping();

        try {
            const response = await fetch('/api/respond', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, response: message, question: currentQuestion })
            });
            const data = await response.json();
            hideTyping();

            if (data.signals_detected && Object.keys(data.signals_detected).length > 0) {
                const signals = Object.keys(data.signals_detected).join(', ');
                addMessage('system', `Detected: ${signals}`);
            }
            updateProgress(data.progress);
            await getNextQuestion();
        } catch (error) {
            hideTyping();
            console.error('Error:', error);
            addMessage('system', 'Sorry, there was an error processing your response.');
        }
    }

    async function skipQuestion() {
        if (!currentQuestion) return;
        if (isRecording) stopRecording();
        addMessage('user', '[Skipped]');
        try {
            await fetch('/api/skip', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, question: currentQuestion })
            });
            await getNextQuestion();
        } catch (error) { console.error('Error:', error); }
    }

    async function endInterview() {
        if (!confirm('End the interview now? You can still download results.')) return;
        if (isRecording) stopRecording();
        stopSpeaking();
        try {
            const response = await fetch('/api/end', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId })
            });
            const data = await response.json();
            showSummary(data.summary);
        } catch (error) { console.error('Error:', error); }
    }

    const SVG_BOT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2Z" opacity=".3"/></svg>';
    const SVG_USER = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>';

    function addMessage(type, content, extraClass = '') {
        const messagesDiv = document.getElementById('chat-messages');
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${type}`;
        if (type === 'system') {
            messageDiv.innerHTML = `<div class="message-content">${content}</div>`;
        } else {
            const cc = extraClass ? `message-content ${extraClass}` : 'message-content';
            messageDiv.innerHTML = `
                <div class="message-avatar">${type === 'bot' ? SVG_BOT : SVG_USER}</div>
                <div class="${cc}">${content}</div>`;
        }
        messagesDiv.appendChild(messageDiv);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }

    function showTyping() {
        const messagesDiv = document.getElementById('chat-messages');
        const div = document.createElement('div');
        div.id = 'typing-indicator'; div.className = 'message bot';
        div.innerHTML = `<div class="message-avatar">${SVG_BOT}</div><div class="message-content"><div class="typing-indicator"><span></span><span></span><span></span></div></div>`;
        messagesDiv.appendChild(div);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
    }
    function hideTyping() {
        const t = document.getElementById('typing-indicator');
        if (t) t.remove();
    }

    function updateProgress(progress) {
        if (!progress) return;

        document.getElementById('progress-percent').textContent = progress.overall_percent + '%';
        document.getElementById('progress-bar').style.width = progress.overall_percent + '%';
        document.getElementById('current-phase').textContent = progress.phase || '';

        const s = document.getElementById('phase-scoping');
        const d = document.getElementById('phase-domains');
        const u = document.getElementById('phase-summary');

        [s, d, u].forEach(el => { el.className = 'pdot'; });

        if (progress.phase === 'Scoping') {
            s.classList.add('active');
        } else if (progress.phase && progress.phase.startsWith('Expert')) {
            s.classList.add('done'); d.classList.add('active');
        } else {
            s.classList.add('done'); d.classList.add('done'); u.classList.add('active');
        }

        const pillsDiv = document.getElementById('domain-pills');
        pillsDiv.innerHTML = '';

        if (progress.current_domain) {
            const p = document.createElement('span'); p.className = 'domain-pill active';
            p.textContent = progress.current_domain.charAt(0).toUpperCase() + progress.current_domain.slice(1);
            pillsDiv.appendChild(p);
        }
        for (const domain of progress.domains_completed || []) {
            if (domain === progress.current_domain) continue;
            const p = document.createElement('span'); p.className = 'domain-pill completed';
            p.textContent = domain.charAt(0).toUpperCase() + domain.slice(1);
            pillsDiv.appendChild(p);
        }
        for (const domain of progress.domains_pending || []) {
            const p = document.createElement('span'); p.className = 'domain-pill pending';
            p.textContent = domain.charAt(0).toUpperCase() + domain.slice(1);
            pillsDiv.appendChild(p);
        }
    }

    // Markdown → HTML for PRD
    function markdownToHtml(md) {
        let html = md;
        html = html.replace(/```([\\s\\S]*?)```/g, (m, code) =>
            '<pre><code>' + code.replace(/</g,'&lt;').replace(/>/g,'&gt;').trim() + '</code></pre>');
        html = html.replace(/((?:^\\|.+\\|$\\n?)+)/gm, (block) => {
            const rows = block.trim().split('\\n').filter(r => r.trim());
            if (rows.length < 2) return block;
            const isSep = /^[\\s|:-]+$/.test(rows[1]);
            let out = '<table>';
            rows.forEach((row, idx) => {
                if (idx === 1 && isSep) return;
                const cells = row.split('|').filter((c,i,a) => i>0 && i<a.length-1);
                const tag = (idx===0 && isSep) ? 'th' : 'td';
                out += '<tr>' + cells.map(c => `<${tag}>${c.trim()}</${tag}>`).join('') + '</tr>';
            });
            return out + '</table>';
        });
        html = html.replace(/^### (.+)$/gm,'<h3>$1</h3>');
        html = html.replace(/^## (.+)$/gm,'<h2>$1</h2>');
        html = html.replace(/^# (.+)$/gm,'<h1>$1</h1>');
        html = html.replace(/\\*\\*(.+?)\\*\\*/g,'<strong>$1</strong>');
        html = html.replace(/`([^`]+)`/g,'<code>$1</code>');
        html = html.replace(/^- \\[ \\] (.+)$/gm,'<li><input type="checkbox" disabled> $1</li>');
        html = html.replace(/^- \\[x\\] (.+)$/gm,'<li><input type="checkbox" checked disabled> $1</li>');
        html = html.replace(/^- (.+)$/gm,'<li>$1</li>');
        html = html.replace(/((?:<li>.*<\\/li>\\n?)+)/g,'<ul>$1</ul>');
        html = html.split('\\n').map(line => {
            const t = line.trim();
            if (!t) return '';
            if (t.startsWith('<')) return t;
            return `<p>${t}</p>`;
        }).join('\\n');
        return html;
    }

    let prdMarkdown = null;
    let prdJson = null;

    async function showSummary(summary) {
        document.getElementById('chat-container').classList.remove('active');
        document.getElementById('summary').classList.add('active');
        interviewData = summary;

        // Company section
        const sec = document.createElement('div'); sec.className = 'sum-section';
        const h4 = document.createElement('h4'); h4.textContent = 'Company'; sec.appendChild(h4);
        const p1 = document.createElement('p');
        const strong = document.createElement('strong'); strong.textContent = summary.client_name || ''; p1.appendChild(strong);
        p1.appendChild(document.createTextNode(' (' + (summary.industry || '') + ')')); sec.appendChild(p1);
        const p2 = document.createElement('p'); p2.textContent = 'Questions answered: ' + (summary.questions_asked || 0); sec.appendChild(p2);
        const domains = (summary.domains_covered || []).map(d => d.charAt(0).toUpperCase() + d.slice(1)).join(', ') || 'None';
        const p3 = document.createElement('p'); p3.textContent = 'Domains covered: ' + domains; sec.appendChild(p3);
        const sumEl = document.getElementById('summary-content');
        sumEl.textContent = ''; sumEl.appendChild(sec);

        document.getElementById('prd-content').innerHTML = `
            <div class="prd-loading">
                <div class="prd-spinner"></div>
                <p>Generating Implementation PRD&hellip;</p>
            </div>`;

        speak('Interview complete! Generating your implementation document for ' + summary.client_name + '.');

        try {
            const response = await fetch('/api/generate-prd', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ summary: summary })
            });
            const data = await response.json();
            if (data.error) {
                document.getElementById('prd-content').innerHTML = `<div class="sum-section" style="color:var(--red-text)"><p>Error generating PRD: ${data.error}</p></div>`;
                return;
            }
            prdMarkdown = data.markdown; prdJson = data.json;
            document.getElementById('prd-content').innerHTML = `<div class="prd-container">${markdownToHtml(data.markdown)}</div>`;

            // Show action buttons
            document.getElementById('btn-download-md').style.display = '';
            document.getElementById('btn-download-json').style.display = '';
            document.getElementById('deploy-target-label').style.display = '';
            document.getElementById('deploy-target').style.display = '';
            const deployRow = document.getElementById('deploy-target-row');
            if (deployRow) deployRow.style.display = 'flex';
            document.getElementById('btn-deploy').style.display = '';
            updateDeployButton();
        } catch (err) {
            console.error('PRD error:', err);
            document.getElementById('prd-content').innerHTML = `<div class="sum-section"><p style="color:var(--text-2)">Failed to generate PRD. You can still download raw interview results.</p></div>`;
        }
    }

    function downloadPrdMarkdown() {
        if (!prdMarkdown) return;
        const name = (interviewData?.client_name || 'company').replace(/\\s+/g,'-');
        const blob = new Blob([prdMarkdown], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = `prd-${name}.md`; a.click();
        URL.revokeObjectURL(url);
    }

    function downloadPrdJson() {
        if (!prdJson) return;
        const name = (interviewData?.client_name || 'company').replace(/\\s+/g,'-');
        const blob = new Blob([JSON.stringify(prdJson, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url; a.download = `prd-${name}.json`; a.click();
        URL.revokeObjectURL(url);
    }

    function startOver() { location.reload(); }
    function handleKeyPress(event) { if (event.key === 'Enter') sendMessage(); }

    if (hasSpeechSynthesis) {
        speechSynthesis.onvoiceschanged = () => { speechSynthesis.getVoices(); };
    }

    // ── Deploy ──
    let buildId = null;
    let pollTimer = null;
    let deployInProgress = false;
    let deployStopped = false;
    let pollErrorCount = 0;
    const MAX_POLL_ERRORS = 10;

    function escapeHtml(str) { const d = document.createElement('div'); d.textContent = str; return d.innerHTML; }

    function updateDeployButton() {
        const sel = document.getElementById('deploy-target');
        const btn = document.getElementById('btn-deploy');
        if (!btn || !sel) return;
        btn.textContent = sel.value === 'railway' ? 'Deploy to Railway' : 'Deploy to Docker';
    }

    async function startDeploy() {
        if (deployInProgress) return;
        if (!prdJson) { alert('No PRD data available. Please generate the PRD first.'); return; }
        deployInProgress = true; deployStopped = false; pollErrorCount = 0; buildId = null;

        document.getElementById('btn-deploy').disabled = true;
        document.getElementById('deploy-target').disabled = true;
        document.getElementById('deploy-panel').classList.add('active');
        document.getElementById('deploy-success').style.display = 'none';
        document.getElementById('deploy-error').style.display = 'none';
        document.getElementById('deploy-log').textContent = '';
        document.getElementById('deploy-tasks').innerHTML = '';
        document.getElementById('btn-stop-deploy').style.display = '';
        document.getElementById('deploy-panel').scrollIntoView({behavior:'smooth'});
        document.getElementById('deploy-progress-fill').style.width = '0%';
        document.getElementById('deploy-percent').textContent = '0%';
        document.getElementById('deploy-status-text').textContent = 'Starting deployment...';

        try {
            const deployTarget = document.getElementById('deploy-target')?.value || 'docker';
            const response = await fetch('/api/build/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ spec: prdJson, deploy_target: deployTarget })
            });
            if (!response.ok) {
                let errorMsg = 'Failed to start build (HTTP ' + response.status + ')';
                try { const err = await response.json(); if (err.error) errorMsg = err.error + ' (HTTP ' + response.status + ')'; } catch(e) {}
                throw new Error(errorMsg);
            }
            const data = await response.json();
            buildId = data.build_id;
            pollTimer = setInterval(pollBuildStatus, 2000);
        } catch (err) {
            document.getElementById('deploy-error').style.display = 'block';
            document.getElementById('deploy-error').textContent = 'Failed to start deploy: ' + err.message;
            document.getElementById('btn-deploy').disabled = false;
            document.getElementById('deploy-target').disabled = false;
            deployInProgress = false; buildId = null;
        }
    }

    async function pollBuildStatus() {
        if (!buildId || deployStopped) return;
        try {
            const response = await fetch(`/api/build/status?build_id=${buildId}`);
            if (!response.ok) {
                pollErrorCount++;
                if (pollErrorCount >= MAX_POLL_ERRORS) {
                    clearInterval(pollTimer); pollTimer = null; deployInProgress = false;
                    document.getElementById('deploy-error').style.display = 'block';
                    document.getElementById('deploy-error').textContent = 'Lost connection to server. Please check and retry.';
                    document.getElementById('btn-deploy').disabled = false;
                    document.getElementById('deploy-target').disabled = false;
                }
                return;
            }
            pollErrorCount = 0;
            const state = await response.json();
            if (deployStopped) return;
            renderBuildState(state);
            if (state.status === 'completed' || state.status === 'failed') {
                clearInterval(pollTimer); pollTimer = null; deployInProgress = false;
            }
        } catch (err) {
            pollErrorCount++;
            if (pollErrorCount >= MAX_POLL_ERRORS) {
                clearInterval(pollTimer); pollTimer = null; deployInProgress = false;
                document.getElementById('deploy-error').style.display = 'block';
                document.getElementById('deploy-error').textContent = 'Lost connection to server. Please check and retry.';
                document.getElementById('btn-deploy').disabled = false;
                document.getElementById('deploy-target').disabled = false;
            }
        }
    }

    function renderBuildState(state) {
        const pct = state.overall_progress || 0;
        document.getElementById('deploy-percent').textContent = pct + '%';
        document.getElementById('deploy-progress-fill').style.width = pct + '%';
        const bar = document.getElementById('deploy-progress-fill').parentElement;
        if (bar) bar.setAttribute('aria-valuenow', pct);

        const statusEl = document.getElementById('deploy-status-text');
        if (state.status === 'completed') statusEl.textContent = 'Deployment Complete!';
        else if (state.status === 'failed') statusEl.textContent = 'Deployment Failed';
        else if (state.current_task) statusEl.textContent = state.current_task.name + '...';

        const taskIcons = {
            completed: '<svg viewBox="0 0 24 24" fill="none" stroke="#1a7f37" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10" opacity=".15" fill="#34c759"/><polyline points="9 12 11.5 14.5 15.5 9.5"/></svg>',
            in_progress: '<svg viewBox="0 0 24 24" fill="none" stroke="#0071e3" stroke-width="2"><circle cx="12" cy="12" r="10" opacity=".15" fill="#0071e3"/><path d="M12 6v6l4 2"/></svg>',
            failed: '<svg viewBox="0 0 24 24" fill="none" stroke="#c62828" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10" opacity=".15" fill="#ff3b30"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>',
            skipped: '<svg viewBox="0 0 24 24" fill="none" stroke="#6e6e73" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="10" opacity=".08" fill="#6e6e73"/><line x1="5" y1="12" x2="19" y2="12"/></svg>',
            pending: '<svg viewBox="0 0 24 24" fill="none" stroke="#aeaeb2" stroke-width="1.5"><circle cx="12" cy="12" r="10"/></svg>'
        };

        const tasksEl = document.getElementById('deploy-tasks');
        tasksEl.innerHTML = '';
        for (const task of (state.tasks || [])) {
            const div = document.createElement('div'); div.className = 'deploy-task';
            const icon = document.createElement('span'); icon.className = 'deploy-task-icon'; icon.innerHTML = taskIcons[task.status] || taskIcons.pending;
            const name = document.createElement('span'); name.className = 'deploy-task-name'; name.textContent = task.name;
            const prog = document.createElement('span'); prog.className = 'deploy-task-progress'; prog.textContent = task.progress + '%';
            div.appendChild(icon); div.appendChild(name); div.appendChild(prog);
            tasksEl.appendChild(div);
        }

        const logEl = document.getElementById('deploy-log');
        let allLogs = [];
        for (const task of (state.tasks || [])) {
            for (const log of (task.logs || [])) allLogs.push('[' + task.name + '] ' + log);
        }
        logEl.textContent = allLogs.join('\\n');
        logEl.scrollTop = logEl.scrollHeight;

        if (state.status === 'completed') {
            const successEl = document.getElementById('deploy-success');
            successEl.style.display = 'block'; successEl.textContent = '';
            const url = state.odoo_url || ('http://localhost:' + (state.odoo_port || 8069));
            const s = document.createElement('strong'); s.textContent = 'Odoo is running!'; successEl.appendChild(s);
            successEl.appendChild(document.createElement('br'));
            const link = document.createElement('a'); link.textContent = url;
            if (/^https?:\\/\\//.test(url)) { link.href = url; link.target = '_blank'; }
            successEl.appendChild(link); successEl.appendChild(document.createElement('br'));
            const small = document.createElement('small'); small.textContent = 'Login: admin / admin'; successEl.appendChild(small);
            document.getElementById('btn-stop-deploy').style.display = 'none';
            document.getElementById('btn-deploy').disabled = false;
            document.getElementById('deploy-target').disabled = false;
            deployInProgress = false;
        }

        if (state.status === 'failed') {
            const errorEl = document.getElementById('deploy-error');
            errorEl.style.display = 'block';
            const failedTask = (state.tasks || []).find(t => t.status === 'failed');
            errorEl.textContent = failedTask
                ? 'Failed at: ' + failedTask.name + ' — ' + (failedTask.error_message || 'Unknown error')
                : 'Build failed';
            document.getElementById('btn-deploy').disabled = false;
            document.getElementById('deploy-target').disabled = false;
            deployInProgress = false;
        }
    }

    async function stopDeploy() {
        deployStopped = true;
        if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
        if (!buildId) return;
        document.getElementById('btn-stop-deploy').disabled = true;
        let stopFailed = false;
        try {
            const response = await fetch('/api/build/stop', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ build_id: buildId })
            });
            if (!response.ok) {
                document.getElementById('deploy-status-text').textContent = 'Warning: stop request failed (HTTP ' + response.status + ')';
                stopFailed = true;
            }
        } catch (err) {
            document.getElementById('deploy-status-text').textContent = 'Warning: stop request failed (network error)';
            stopFailed = true;
        }
        if (!stopFailed) document.getElementById('deploy-status-text').textContent = 'Stopped';
        document.getElementById('btn-stop-deploy').style.display = 'none';
        document.getElementById('btn-deploy').disabled = false;
        document.getElementById('deploy-target').disabled = false;
        deployInProgress = false;
    }

    // ── Auto-load demo result if available ──
    (async function checkDemoResult() {
        try {
            const r = await fetch('/api/demo-result');
            const data = await r.json();
            if (!data.available) return;

            const summary = data.summary;
            const prd = data.prd;

            document.getElementById('setup-form').classList.add('hidden');
            document.getElementById('summary').classList.add('active');

            interviewData = summary;
            prdMarkdown = prd.markdown;
            prdJson = prd.json;

            const sec = document.createElement('div'); sec.className = 'sum-section';
            const h4 = document.createElement('h4'); h4.textContent = 'Company'; sec.appendChild(h4);
            const p1 = document.createElement('p');
            const strong = document.createElement('strong'); strong.textContent = summary.client_name || ''; p1.appendChild(strong);
            p1.appendChild(document.createTextNode(' (' + (summary.industry || '') + ')')); sec.appendChild(p1);
            const p2 = document.createElement('p'); p2.textContent = 'Questions answered: ' + (summary.questions_asked || 0); sec.appendChild(p2);
            const domains = (summary.domains_covered || []).map(d => d.charAt(0).toUpperCase() + d.slice(1)).join(', ') || 'None';
            const p3 = document.createElement('p'); p3.textContent = 'Domains covered: ' + domains; sec.appendChild(p3);
            const sumEl = document.getElementById('summary-content'); sumEl.textContent = ''; sumEl.appendChild(sec);

            document.getElementById('prd-content').innerHTML = `<div class="prd-container">${markdownToHtml(prd.markdown)}</div>`;

            document.getElementById('btn-download-md').style.display = '';
            document.getElementById('btn-download-json').style.display = '';
            document.getElementById('deploy-target-label').style.display = '';
            document.getElementById('deploy-target').style.display = '';
            const deployRow = document.getElementById('deploy-target-row');
            if (deployRow) deployRow.style.display = 'flex';
            document.getElementById('btn-deploy').style.display = '';
            updateDeployButton();
        } catch (e) {
            // No demo result — show normal setup form
        }
    })();
</script>
</body>
</html>
"""


@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/start', methods=['POST'])
def start_interview():
    data = request.json
    client_name = data.get('client_name', 'Unknown')
    industry = data.get('industry', 'General')

    session_id = secrets.token_hex(8)

    _out = "/tmp" if os.environ.get("VERCEL") else "./outputs"
    agent = PhasedInterviewAgent(
        client_name=client_name,
        industry=industry,
        output_dir=_out
    )

    agents[session_id] = {
        'agent': agent,
        'client_name': client_name,
        'industry': industry
    }

    return jsonify({
        'session_id': session_id,
        'client_name': client_name,
        'industry': industry
    })


@app.route('/api/question', methods=['GET'])
def get_question():
    session_id = request.args.get('session_id')

    if session_id not in agents:
        return jsonify({'error': 'Invalid session'}), 400

    agent = agents[session_id]['agent']

    question_data = agent.get_next_question()

    if question_data is None or agent.is_complete():
        summary = agent.get_summary()
        agent.save_interview()
        return jsonify({
            'complete': True,
            'summary': summary
        })

    return jsonify({
        'complete': False,
        'id': question_data['id'],
        'question': question_data['text'],
        'phase': question_data['phase'],
        'domain': question_data.get('domain'),
        'context': question_data.get('context'),
        'expert_intro': question_data.get('expert_intro'),
        'progress': question_data['progress']
    })


@app.route('/api/respond', methods=['POST'])
def respond():
    data = request.json
    session_id = data.get('session_id')
    response_text = data.get('response', '')
    question_info = data.get('question', {})

    if session_id not in agents:
        return jsonify({'error': 'Invalid session'}), 400

    agent = agents[session_id]['agent']

    result = agent.process_response(response_text, question_info)

    return jsonify({
        'signals_detected': result.get('signals_detected', {}),
        'progress': result.get('progress', {}),
        'domains_active': result.get('domains_active', [])
    })


@app.route('/api/skip', methods=['POST'])
def skip_question():
    data = request.json
    session_id = data.get('session_id')
    question_info = data.get('question', {})

    if session_id not in agents:
        return jsonify({'error': 'Invalid session'}), 400

    agent = agents[session_id]['agent']
    agent.skip_question(question_info)

    return jsonify({'skipped': True})


@app.route('/api/end', methods=['POST'])
def end_interview():
    data = request.json
    session_id = data.get('session_id')

    if session_id not in agents:
        return jsonify({'error': 'Invalid session'}), 400

    agent = agents[session_id]['agent']
    filepath = agent.save_interview()
    summary = agent.get_summary()

    return jsonify({
        'summary': summary,
        'filepath': filepath
    })


@app.route('/api/generate-prd', methods=['POST'])
def generate_prd():
    """Generate a PRD document from interview summary."""
    data = request.json
    summary = data.get('summary', {})

    if not summary:
        return jsonify({'error': 'No summary provided'}), 400

    try:
        spec = create_spec_from_interview(summary)
        result = {
            'markdown': spec.to_markdown(),
            'json': spec.to_dict(),
            'company_name': spec.company.name,
            'module_count': len(spec.modules),
            'estimated_minutes': spec.get_total_estimated_time(),
        }
        # Store for /api/demo-result so the browser can auto-load it
        global last_demo_result
        last_demo_result = {'summary': summary, 'prd': result}
        return jsonify(result)
    except Exception as e:
        print(f"PRD generation error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/demo-result', methods=['GET'])
def demo_result():
    """Return the last completed PRD result, if any."""
    if last_demo_result is None:
        return jsonify({'available': False})
    return jsonify({'available': True, **last_demo_result})


@app.route('/api/transcribe', methods=['POST'])
def transcribe_audio():
    """Transcribe audio using Whisper (server-side)."""
    global whisper_model

    data = request.json
    audio_b64 = data.get('audio', '')

    if not audio_b64:
        return jsonify({'error': 'No audio data'}), 400

    if not WHISPER_AVAILABLE:
        return jsonify({'error': 'Whisper not available', 'text': ''}), 200

    try:
        # Decode base64 audio
        audio_bytes = base64.b64decode(audio_b64)

        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        # Lazy load whisper model
        if whisper_model is None:
            print("Loading Whisper model (first request)...")
            whisper_model = SpeechToText(model_size="base", language="en")

        # Transcribe
        result = whisper_model.transcribe_file(temp_path)

        # Clean up
        Path(temp_path).unlink(missing_ok=True)

        return jsonify({'text': result.text})

    except Exception as e:
        print(f"Transcription error: {e}")
        return jsonify({'error': str(e), 'text': ''}), 200


@app.route('/api/tts', methods=['POST'])
def text_to_speech():
    """Generate speech audio using ElevenLabs (returns MP3)."""
    import os

    api_key = os.environ.get('ELEVENLABS_API_KEY')
    if not api_key:
        return jsonify({'error': 'ElevenLabs not configured'}), 200

    data = request.json
    text = data.get('text', '')
    if not text:
        return jsonify({'error': 'No text provided'}), 400

    try:
        from src.voice.text_to_speech import TextToSpeech
        tts = TextToSpeech(elevenlabs_api_key=api_key)
        audio_bytes = tts.generate_audio(text)
        if not audio_bytes:
            return jsonify({'error': 'No audio generated'}), 200

        return Response(audio_bytes, mimetype='audio/mpeg')

    except Exception as e:
        print(f"TTS error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/tts/status', methods=['GET'])
def tts_status():
    """Check if ElevenLabs TTS is available."""
    import os
    available = bool(os.environ.get('ELEVENLABS_API_KEY'))
    return jsonify({'elevenlabs': available})


BUILD_TTL_SECONDS = 3600  # Prune completed builds after 1 hour
BUILD_IN_PROGRESS_TIMEOUT_SECONDS = 15 * 60


def _prune_old_builds():
    """Remove completed/failed builds older than BUILD_TTL_SECONDS."""
    now = datetime.now()
    to_remove = []
    from src.builders.odoo_builder import TaskStatus
    for bid, builder in builds.items():
        state = builder.state
        status_value = state.status.value if hasattr(state.status, "value") else str(state.status)

        if status_value == "in_progress" and state.started_at:
            try:
                started = datetime.fromisoformat(state.started_at)
                if (now - started).total_seconds() > BUILD_IN_PROGRESS_TIMEOUT_SECONDS:
                    try:
                        builder.stop()
                    except Exception as e:
                        print(f"Warning: could not stop build {bid}: {e}")
                    state.status = TaskStatus.FAILED
                    state.error_message = "Build timed out after 15 minutes"
                    state.completed_at = now.isoformat()
            except (ValueError, TypeError):
                pass

        if state.completed_at:
            try:
                completed = datetime.fromisoformat(state.completed_at)
                if (now - completed).total_seconds() > BUILD_TTL_SECONDS:
                    to_remove.append(bid)
            except (ValueError, TypeError):
                pass
    for bid in to_remove:
        del builds[bid]


@app.route('/api/build/start', methods=['POST'])
def build_start():
    """Start an Odoo build from an ImplementationSpec."""
    from src.schemas.implementation_spec import ImplementationSpec
    from src.builders.odoo_builder import OdooBuilder, TaskStatus

    data = request.json
    if data is None:
        return jsonify({'error': 'Request body must be JSON'}), 400

    spec_data = data.get('spec')
    if not spec_data or not isinstance(spec_data, dict):
        return jsonify({'error': 'No spec provided'}), 400

    try:
        spec = ImplementationSpec.from_dict(spec_data)
    except Exception as e:
        return jsonify({'error': f'Invalid spec: {e}'}), 400

    deploy_target = data.get('deploy_target', 'docker')
    if deploy_target not in ('docker', 'railway'):
        return jsonify({'error': 'Invalid deploy target'}), 400

    with builds_lock:
        # Guard: only one active build at a time
        active = [b for b in builds.values()
                  if b.state.status.value in ('pending', 'in_progress')]
        if active:
            return jsonify({'error': 'A build is already running'}), 409

        # Prune old completed builds
        _prune_old_builds()

        if deploy_target == 'railway':
            from src.builders.railway_builder import RailwayOdooBuilder
            railway_token = os.environ.get('RAILWAY_API_TOKEN', '')
            if not railway_token:
                return jsonify({
                    'error': (
                        'RAILWAY_API_TOKEN not set. Add it to your .env file or environment. '
                        'Get a token at https://railway.app/account/tokens'
                    )
                }), 400
            builder = RailwayOdooBuilder(spec, railway_token)
        else:
            builder = OdooBuilder(spec)

        build_id = builder.state.build_id
        builds[build_id] = builder

    def run_build():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(builder.build())
        except Exception as e:
            builder.state.status = TaskStatus.FAILED
            builder.state.completed_at = datetime.now().isoformat()
            print(f"Build {build_id} failed with exception: {e}")
        finally:
            loop.close()

    thread = threading.Thread(target=run_build, daemon=True)
    thread.start()

    return jsonify({'build_id': build_id})


@app.route('/api/build/status', methods=['GET'])
def build_status():
    """Get the current build state."""
    build_id = request.args.get('build_id')
    if not build_id:
        return jsonify({'error': 'No build_id provided'}), 400

    with builds_lock:
        builder = builds.get(build_id)

    if not builder:
        return jsonify({'error': 'Build not found'}), 404

    return jsonify(builder.state.to_dict())


@app.route('/api/build/stop', methods=['POST'])
def build_stop():
    """Stop a running build."""
    data = request.json
    if data is None:
        return jsonify({'error': 'Request body must be JSON'}), 400

    build_id = data.get('build_id')
    if not build_id:
        return jsonify({'error': 'No build_id provided'}), 400

    with builds_lock:
        builder = builds.get(build_id)

    if not builder:
        return jsonify({'error': 'Build not found'}), 404

    builder.stop()
    return jsonify({'stopped': True})


if __name__ == '__main__':
    print("""
╔═══════════════════════════════════════════════════════════════╗
║     ODOO IMPLEMENTATION INTERVIEW - WITH VOICE SUPPORT         ║
╠═══════════════════════════════════════════════════════════════╣
║  Voice Input: Browser microphone → Whisper transcription       ║
║  Voice Output: Browser text-to-speech                          ║
║  Also works with keyboard input                                ║
╠═══════════════════════════════════════════════════════════════╣
║  Phase 1: Scoping - Determine your business scope              ║
║  Phase 2: Domain Experts - Deep-dive with specialists          ║
║  Phase 3: Summary - Module recommendations                     ║
╚═══════════════════════════════════════════════════════════════╝

Starting web server...

Open your browser to: http://localhost:5001

Press Ctrl+C to stop the server.
    """)

    app.run(debug=True, host='0.0.0.0', port=5001)
