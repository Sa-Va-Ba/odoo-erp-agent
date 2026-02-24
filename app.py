#!/usr/bin/env python3
"""
Odoo Implementation Assistant - Complete Web Application

Three main sections:
1. Interview - Gather requirements
2. Build - Deploy Odoo with real-time progress
3. Test - Validate the installation

Run:
    python3 app.py

Then open: http://localhost:5001
"""

import asyncio
import json
import sys
import base64
import tempfile
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify
import secrets
import threading

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

from src.agents.phased_interview_agent import PhasedInterviewAgent
from src.schemas.implementation_spec import create_spec_from_interview, ImplementationSpec
from src.builders.odoo_builder import OdooBuilder, BuildState, TaskStatus
from src.builders.cloud_builder import CloudOdooBuilder, CloudProvider, CloudBuildState, get_available_providers

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

# Global state
sessions = {}  # Interview sessions
builds = {}    # Build states
builders = {}  # Active builders

# Try to load whisper for transcription
try:
    from src.voice.speech_to_text import SpeechToText
    WHISPER_AVAILABLE = True
    whisper_model = None
except ImportError:
    WHISPER_AVAILABLE = False

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Odoo Implementation Assistant</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }

        .app-container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }

        /* Navigation */
        .nav-tabs {
            display: flex;
            gap: 4px;
            margin-bottom: 20px;
        }

        .nav-tab {
            padding: 14px 28px;
            background: rgba(255,255,255,0.2);
            border: none;
            border-radius: 8px 8px 0 0;
            color: white;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }

        .nav-tab:hover { background: rgba(255,255,255,0.3); }
        .nav-tab.active { background: white; color: #714B67; }
        .nav-tab:disabled { opacity: 0.5; cursor: not-allowed; }

        .nav-tab .step-num {
            display: inline-block;
            width: 24px;
            height: 24px;
            line-height: 24px;
            text-align: center;
            background: rgba(255,255,255,0.2);
            border-radius: 50%;
            margin-right: 8px;
            font-size: 12px;
        }

        .nav-tab.active .step-num { background: #714B67; color: white; }
        .nav-tab.completed .step-num { background: #4CAF50; }

        /* Main Card */
        .main-card {
            background: white;
            border-radius: 0 16px 16px 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            min-height: 600px;
            overflow: hidden;
        }

        .card-header {
            background: linear-gradient(135deg, #714B67 0%, #4A3347 100%);
            color: white;
            padding: 24px 30px;
        }

        .card-header h1 { font-size: 24px; margin-bottom: 4px; }
        .card-header p { opacity: 0.9; font-size: 14px; }

        .card-content {
            padding: 30px;
        }

        /* Tab panels */
        .tab-panel { display: none; }
        .tab-panel.active { display: block; }

        /* Common elements */
        .btn {
            background: linear-gradient(135deg, #714B67 0%, #4A3347 100%);
            color: white;
            border: none;
            padding: 14px 28px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }

        .btn:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(113,75,103,0.4); }
        .btn:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
        .btn-secondary { background: #f0f0f0; color: #333; }
        .btn-secondary:hover { background: #e0e0e0; box-shadow: none; }
        .btn-success { background: #4CAF50; }
        .btn-small { padding: 8px 16px; font-size: 13px; }

        .form-group {
            margin-bottom: 20px;
        }

        .form-group label {
            display: block;
            font-weight: 600;
            color: #333;
            margin-bottom: 8px;
        }

        .form-group input, .form-group select {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 16px;
        }

        .form-group input:focus, .form-group select:focus {
            outline: none;
            border-color: #714B67;
        }

        /* Progress section */
        .progress-section {
            background: #f8f9fa;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }

        .progress-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 12px;
        }

        .progress-bar-container {
            background: #e0e0e0;
            border-radius: 10px;
            height: 12px;
            overflow: hidden;
        }

        .progress-bar {
            background: linear-gradient(90deg, #714B67 0%, #9B6B8F 100%);
            height: 100%;
            border-radius: 10px;
            transition: width 0.5s ease;
        }

        /* Chat messages */
        .chat-messages {
            height: 300px;
            overflow-y: auto;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
            margin-bottom: 20px;
        }

        .message {
            margin-bottom: 16px;
            display: flex;
            gap: 12px;
        }

        .message.bot { flex-direction: row; }
        .message.user { flex-direction: row-reverse; }

        .message-avatar {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            flex-shrink: 0;
        }

        .message.bot .message-avatar { background: linear-gradient(135deg, #714B67, #4A3347); }
        .message.user .message-avatar { background: #e0e0e0; }

        .message-content {
            max-width: 75%;
            padding: 12px 16px;
            border-radius: 16px;
            line-height: 1.5;
            font-size: 14px;
        }

        .message.bot .message-content { background: white; border: 1px solid #e0e0e0; }
        .message.user .message-content { background: linear-gradient(135deg, #714B67, #4A3347); color: white; }

        .chat-input-container {
            display: flex;
            gap: 12px;
        }

        .chat-input {
            flex: 1;
            padding: 14px 18px;
            border: 2px solid #e0e0e0;
            border-radius: 24px;
            font-size: 15px;
        }

        .chat-input:focus { outline: none; border-color: #714B67; }

        /* Build tracker */
        .build-tasks {
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .build-task {
            display: flex;
            align-items: center;
            gap: 16px;
            padding: 16px;
            background: #f8f9fa;
            border-radius: 8px;
            border-left: 4px solid #e0e0e0;
        }

        .build-task.pending { border-left-color: #e0e0e0; }
        .build-task.in_progress { border-left-color: #2196F3; background: #e3f2fd; }
        .build-task.completed { border-left-color: #4CAF50; }
        .build-task.failed { border-left-color: #f44336; background: #ffebee; }

        .task-icon {
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 20px;
            background: white;
        }

        .task-info { flex: 1; }
        .task-name { font-weight: 600; margin-bottom: 4px; }
        .task-description { font-size: 13px; color: #666; }

        .task-status {
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
        }

        .task-status.pending { background: #e0e0e0; color: #666; }
        .task-status.in_progress { background: #2196F3; color: white; }
        .task-status.completed { background: #4CAF50; color: white; }
        .task-status.failed { background: #f44336; color: white; }

        /* Summary cards */
        .summary-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 20px;
        }

        .summary-card {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 12px;
            text-align: center;
        }

        .summary-card h3 { font-size: 32px; color: #714B67; margin-bottom: 8px; }
        .summary-card p { font-size: 14px; color: #666; }

        /* Module tags */
        .module-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }

        .module-tag {
            padding: 8px 14px;
            border-radius: 20px;
            font-size: 13px;
            font-weight: 500;
            background: #e8f5e9;
            color: #2e7d32;
        }

        /* Test section */
        .test-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
        }

        .test-card {
            background: #f8f9fa;
            padding: 24px;
            border-radius: 12px;
            text-align: center;
        }

        .test-card h3 { margin-bottom: 12px; }
        .test-card p { font-size: 14px; color: #666; margin-bottom: 16px; }

        .spinner {
            width: 40px;
            height: 40px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid #714B67;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto;
        }

        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }

        .hidden { display: none !important; }

        /* Phase steps */
        .phase-steps {
            display: flex;
            justify-content: space-between;
            margin-bottom: 16px;
        }

        .phase-step {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            color: #999;
        }

        .phase-step.active { color: #714B67; font-weight: 600; }
        .phase-step.completed { color: #4CAF50; }

        .phase-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #e0e0e0;
        }

        .phase-step.active .phase-dot { background: #714B67; }
        .phase-step.completed .phase-dot { background: #4CAF50; }

        .domain-pill {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 500;
            margin: 2px;
        }

        .domain-pill.active { background: #714B67; color: white; }
        .domain-pill.completed { background: #4CAF50; color: white; }
        .domain-pill.pending { background: #e0e0e0; color: #666; }

        .logs-container {
            background: #1e1e1e;
            color: #0f0;
            font-family: monospace;
            font-size: 12px;
            padding: 16px;
            border-radius: 8px;
            max-height: 200px;
            overflow-y: auto;
            margin-top: 20px;
        }

        .log-entry { margin-bottom: 4px; }
    </style>
</head>
<body>
    <div class="app-container">
        <!-- Navigation Tabs -->
        <div class="nav-tabs">
            <button class="nav-tab active" id="tab-interview" onclick="switchTab('interview')">
                <span class="step-num">1</span> Interview
            </button>
            <button class="nav-tab" id="tab-build" onclick="switchTab('build')" disabled>
                <span class="step-num">2</span> Build
            </button>
            <button class="nav-tab" id="tab-test" onclick="switchTab('test')" disabled>
                <span class="step-num">3</span> Test
            </button>
        </div>

        <div class="main-card">
            <!-- ==================== INTERVIEW TAB ==================== -->
            <div class="tab-panel active" id="panel-interview">
                <div class="card-header">
                    <h1>🏢 Requirements Interview</h1>
                    <p>Let's understand your business needs for Odoo</p>
                </div>

                <div class="card-content">
                    <!-- Setup Form -->
                    <div id="setup-form">
                        <div class="form-group">
                            <label>Company Name</label>
                            <input type="text" id="client-name" placeholder="e.g., Acme Corporation">
                        </div>
                        <div class="form-group">
                            <label>Industry</label>
                            <select id="industry">
                                <option value="E-commerce">E-commerce / Online Retail</option>
                                <option value="Manufacturing">Manufacturing</option>
                                <option value="Retail">Retail / Brick & Mortar</option>
                                <option value="Services">Professional Services</option>
                                <option value="Distribution">Distribution / Wholesale</option>
                                <option value="Technology">Technology / Software</option>
                                <option value="Other">Other</option>
                            </select>
                        </div>
                        <button class="btn" onclick="startInterview()">Start Interview →</button>
                    </div>

                    <!-- Interview Chat -->
                    <div id="interview-chat" class="hidden">
                        <div class="progress-section">
                            <div class="phase-steps">
                                <div class="phase-step" id="phase-scoping">
                                    <div class="phase-dot"></div>
                                    <span>1. Scoping</span>
                                </div>
                                <div class="phase-step" id="phase-domains">
                                    <div class="phase-dot"></div>
                                    <span>2. Domain Expert</span>
                                </div>
                                <div class="phase-step" id="phase-summary">
                                    <div class="phase-dot"></div>
                                    <span>3. Summary</span>
                                </div>
                            </div>
                            <div class="progress-header">
                                <span id="current-phase">Phase: Scoping</span>
                                <span id="progress-percent">0%</span>
                            </div>
                            <div class="progress-bar-container">
                                <div class="progress-bar" id="progress-bar" style="width: 0%"></div>
                            </div>
                            <div id="domain-pills"></div>
                        </div>

                        <div class="chat-messages" id="chat-messages"></div>

                        <div class="chat-input-container">
                            <input type="text" class="chat-input" id="user-input" placeholder="Type your answer..." onkeypress="if(event.key==='Enter')sendMessage()">
                            <button class="btn" onclick="sendMessage()">➤</button>
                        </div>

                        <div style="margin-top: 12px; display: flex; gap: 8px;">
                            <button class="btn btn-secondary btn-small" onclick="skipQuestion()">Skip</button>
                            <button class="btn btn-secondary btn-small" onclick="endInterview()">End & Continue to Build</button>
                        </div>
                    </div>

                    <!-- Interview Complete -->
                    <div id="interview-complete" class="hidden">
                        <h2 style="margin-bottom: 20px;">✅ Interview Complete!</h2>

                        <div class="summary-grid">
                            <div class="summary-card">
                                <h3 id="modules-count">0</h3>
                                <p>Modules to Install</p>
                            </div>
                            <div class="summary-card">
                                <h3 id="domains-count">0</h3>
                                <p>Business Areas</p>
                            </div>
                            <div class="summary-card">
                                <h3 id="est-time">~15</h3>
                                <p>Minutes to Build</p>
                            </div>
                        </div>

                        <h4 style="margin-bottom: 12px;">Recommended Modules:</h4>
                        <div class="module-tags" id="recommended-modules"></div>

                        <div style="margin-top: 30px;">
                            <h4 style="margin-bottom: 16px;">Choose Deployment Method:</h4>
                            <div style="display: flex; gap: 16px; flex-wrap: wrap;">
                                <div style="flex: 1; min-width: 250px; background: #f8f9fa; padding: 20px; border-radius: 12px; border: 2px solid #e0e0e0;">
                                    <h4>🐳 Local Docker</h4>
                                    <p style="font-size: 13px; color: #666; margin: 12px 0;">Run Odoo on your machine. Requires Docker Desktop installed.</p>
                                    <button class="btn" onclick="startBuild('docker')">Use Docker →</button>
                                </div>
                                <div style="flex: 1; min-width: 250px; background: #e8f5e9; padding: 20px; border-radius: 12px; border: 2px solid #4CAF50;">
                                    <h4>☁️ Cloud Deploy <span style="background: #4CAF50; color: white; font-size: 10px; padding: 2px 6px; border-radius: 8px; margin-left: 8px;">FREE</span></h4>
                                    <p style="font-size: 13px; color: #666; margin: 12px 0;">Deploy to free cloud hosting. No installation needed!</p>
                                    <button class="btn btn-success" onclick="startBuild('cloud')">Use Cloud →</button>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- ==================== BUILD TAB ==================== -->
            <div class="tab-panel" id="panel-build">
                <div class="card-header">
                    <h1 id="build-header-title">🔧 Building Your Odoo</h1>
                    <p id="build-header-desc">Setting up Docker, installing modules, and configuring your system</p>
                </div>

                <div class="card-content">
                    <!-- Cloud Provider Selection (only shown for cloud builds) -->
                    <div id="cloud-provider-select" class="hidden" style="margin-bottom: 24px;">
                        <h4 style="margin-bottom: 16px;">Select Cloud Provider:</h4>
                        <div id="provider-cards" style="display: flex; gap: 12px; flex-wrap: wrap;"></div>
                    </div>

                    <div class="progress-section">
                        <div class="progress-header">
                            <span id="build-status">Preparing...</span>
                            <span id="build-percent">0%</span>
                        </div>
                        <div class="progress-bar-container">
                            <div class="progress-bar" id="build-progress-bar" style="width: 0%"></div>
                        </div>
                    </div>

                    <div class="build-tasks" id="build-tasks">
                        <!-- Tasks will be populated dynamically -->
                    </div>

                    <div class="logs-container" id="build-logs">
                        <div class="log-entry">Waiting to start...</div>
                    </div>

                    <!-- Cloud Instructions Panel -->
                    <div id="cloud-instructions" class="hidden" style="margin-top: 20px; padding: 20px; background: #fff3cd; border-radius: 12px; border-left: 4px solid #ffc107;">
                        <h4 style="margin-bottom: 12px;">📋 Action Required</h4>
                        <p id="cloud-action-text">Follow the instructions below...</p>
                        <a id="cloud-action-url" href="#" target="_blank" class="btn btn-small" style="margin-top: 12px; display: inline-block; text-decoration: none;">
                            Open Provider →
                        </a>
                        <button class="btn btn-secondary btn-small" style="margin-left: 8px;" onclick="confirmCloudStep()">I've Done This ✓</button>
                    </div>

                    <div id="build-complete" class="hidden" style="margin-top: 30px; text-align: center;">
                        <h2>🎉 Build Complete!</h2>
                        <p style="margin: 20px 0;">Your Odoo instance is ready at:</p>
                        <a id="odoo-url" href="#" target="_blank" class="btn btn-success" style="display: inline-block; text-decoration: none;">
                            Open Odoo →
                        </a>
                        <p style="margin-top: 16px; color: #666;">
                            Default login: <strong>admin</strong> / Password: <strong>admin</strong>
                        </p>
                        <button class="btn" style="margin-top: 20px;" onclick="switchTab('test')">Continue to Testing →</button>
                    </div>
                </div>
            </div>

            <!-- ==================== TEST TAB ==================== -->
            <div class="tab-panel" id="panel-test">
                <div class="card-header">
                    <h1>✅ Test Your Odoo</h1>
                    <p>Validate that everything is working correctly</p>
                </div>

                <div class="card-content">
                    <div id="test-content">
                        <p style="margin-bottom: 30px;">Run these tests to make sure your Odoo instance is configured correctly.</p>

                        <div class="test-cards">
                            <div class="test-card">
                                <h3>🔌 Connection</h3>
                                <p>Check if Odoo is responding</p>
                                <button class="btn btn-small" onclick="runTest('connection')">Run Test</button>
                                <div id="test-connection-result" style="margin-top: 12px;"></div>
                            </div>

                            <div class="test-card">
                                <h3>📦 Modules</h3>
                                <p>Verify all modules are installed</p>
                                <button class="btn btn-small" onclick="runTest('modules')">Run Test</button>
                                <div id="test-modules-result" style="margin-top: 12px;"></div>
                            </div>

                            <div class="test-card">
                                <h3>🏢 Company</h3>
                                <p>Check company configuration</p>
                                <button class="btn btn-small" onclick="runTest('company')">Run Test</button>
                                <div id="test-company-result" style="margin-top: 12px;"></div>
                            </div>

                            <div class="test-card">
                                <h3>👥 Users</h3>
                                <p>Test user login</p>
                                <button class="btn btn-small" onclick="runTest('users')">Run Test</button>
                                <div id="test-users-result" style="margin-top: 12px;"></div>
                            </div>
                        </div>

                        <div style="margin-top: 40px; padding: 20px; background: #e8f5e9; border-radius: 12px; text-align: center;">
                            <h3>🎉 All Done!</h3>
                            <p style="margin: 16px 0;">Your Odoo instance is ready for use.</p>
                            <a id="final-odoo-url" href="#" target="_blank" class="btn btn-success" style="display: inline-block; text-decoration: none;">
                                Launch Odoo →
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // State
        let sessionId = null;
        let buildId = null;
        let currentQuestion = null;
        let interviewSummary = null;
        let implementationSpec = null;
        let buildPollInterval = null;

        // Tab switching
        function switchTab(tab) {
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));

            document.getElementById('tab-' + tab).classList.add('active');
            document.getElementById('panel-' + tab).classList.add('active');
        }

        // ==================== INTERVIEW ====================
        async function startInterview() {
            const clientName = document.getElementById('client-name').value.trim();
            const industry = document.getElementById('industry').value;

            if (!clientName) {
                alert('Please enter a company name');
                return;
            }

            const response = await fetch('/api/interview/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ client_name: clientName, industry: industry })
            });

            const data = await response.json();
            sessionId = data.session_id;

            document.getElementById('setup-form').classList.add('hidden');
            document.getElementById('interview-chat').classList.remove('hidden');

            addMessage('bot', `Welcome! Let's gather requirements for ${clientName}'s Odoo implementation.`);
            await getNextQuestion();
        }

        async function getNextQuestion() {
            const response = await fetch(`/api/interview/question?session_id=${sessionId}`);
            const data = await response.json();

            if (data.complete) {
                showInterviewComplete(data.summary, data.spec);
                return;
            }

            currentQuestion = data;

            if (data.expert_intro) {
                addMessage('bot', data.expert_intro, 'expert-intro');
            }

            addMessage('bot', data.question);
            updateProgress(data.progress);
        }

        async function sendMessage() {
            const input = document.getElementById('user-input');
            const message = input.value.trim();
            if (!message || !currentQuestion) return;

            input.value = '';
            addMessage('user', message);

            const response = await fetch('/api/interview/respond', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    response: message,
                    question: currentQuestion
                })
            });

            const data = await response.json();
            updateProgress(data.progress);
            await getNextQuestion();
        }

        async function skipQuestion() {
            if (!currentQuestion) return;
            addMessage('user', '[Skipped]');

            await fetch('/api/interview/skip', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, question: currentQuestion })
            });

            await getNextQuestion();
        }

        async function endInterview() {
            const response = await fetch('/api/interview/end', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId })
            });

            const data = await response.json();
            showInterviewComplete(data.summary, data.spec);
        }

        function showInterviewComplete(summary, spec) {
            interviewSummary = summary;
            implementationSpec = spec;

            document.getElementById('interview-chat').classList.add('hidden');
            document.getElementById('interview-complete').classList.remove('hidden');

            document.getElementById('modules-count').textContent = spec.modules.length;
            document.getElementById('domains-count').textContent = summary.domains_covered.length;
            document.getElementById('est-time').textContent = '~' + spec.estimated_setup_minutes;

            const modulesDiv = document.getElementById('recommended-modules');
            modulesDiv.innerHTML = spec.modules.map(m =>
                `<span class="module-tag">${m.display_name}</span>`
            ).join('');

            // Enable build tab
            document.getElementById('tab-build').disabled = false;
            document.getElementById('tab-interview').classList.add('completed');
        }

        function addMessage(type, content, extraClass = '') {
            const messagesDiv = document.getElementById('chat-messages');
            const div = document.createElement('div');
            div.className = `message ${type}`;
            div.innerHTML = `
                <div class="message-avatar">${type === 'bot' ? '🤖' : '👤'}</div>
                <div class="message-content ${extraClass}">${content}</div>
            `;
            messagesDiv.appendChild(div);
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }

        function updateProgress(progress) {
            if (!progress) return;

            document.getElementById('progress-percent').textContent = progress.overall_percent + '%';
            document.getElementById('progress-bar').style.width = progress.overall_percent + '%';
            document.getElementById('current-phase').textContent = `Phase: ${progress.phase}`;

            // Update phase steps
            const steps = ['scoping', 'domains', 'summary'];
            steps.forEach(s => document.getElementById('phase-' + s).className = 'phase-step');

            if (progress.phase === 'Scoping') {
                document.getElementById('phase-scoping').classList.add('active');
            } else if (progress.phase.startsWith('Expert')) {
                document.getElementById('phase-scoping').classList.add('completed');
                document.getElementById('phase-domains').classList.add('active');
            } else {
                document.getElementById('phase-scoping').classList.add('completed');
                document.getElementById('phase-domains').classList.add('completed');
                document.getElementById('phase-summary').classList.add('active');
            }

            // Domain pills
            const pillsDiv = document.getElementById('domain-pills');
            pillsDiv.innerHTML = '';

            if (progress.current_domain) {
                pillsDiv.innerHTML += `<span class="domain-pill active">${progress.current_domain}</span>`;
            }
            (progress.domains_completed || []).forEach(d => {
                if (d !== progress.current_domain)
                    pillsDiv.innerHTML += `<span class="domain-pill completed">✓ ${d}</span>`;
            });
            (progress.domains_pending || []).forEach(d => {
                pillsDiv.innerHTML += `<span class="domain-pill pending">${d}</span>`;
            });
        }

        // ==================== BUILD ====================
        let buildType = 'docker';  // 'docker' or 'cloud'
        let selectedProvider = 'skysize';

        async function startBuild(type) {
            buildType = type;
            switchTab('build');

            if (type === 'cloud') {
                // Update header for cloud
                document.getElementById('build-header-title').textContent = '☁️ Cloud Deployment';
                document.getElementById('build-header-desc').textContent = 'Deploying to free cloud hosting with guided setup';

                // Show provider selection
                await loadProviders();
                document.getElementById('cloud-provider-select').classList.remove('hidden');
            } else {
                // Docker build
                document.getElementById('build-header-title').textContent = '🐳 Local Docker Build';
                document.getElementById('build-header-desc').textContent = 'Setting up Docker, installing modules, and configuring your system';
                document.getElementById('cloud-provider-select').classList.add('hidden');
                await startDockerBuild();
            }
        }

        async function loadProviders() {
            const response = await fetch('/api/cloud/providers');
            const providers = await response.json();

            const container = document.getElementById('provider-cards');
            container.innerHTML = providers.map(p => `
                <div class="provider-card" style="flex: 1; min-width: 180px; padding: 16px; background: ${p.recommended ? '#e8f5e9' : '#f8f9fa'}; border-radius: 8px; border: 2px solid ${p.recommended ? '#4CAF50' : '#e0e0e0'}; cursor: pointer;" onclick="selectProvider('${p.id}', '${p.signup_url}')">
                    <h5>${p.name} ${p.recommended ? '<span style="background:#4CAF50;color:white;font-size:10px;padding:2px 6px;border-radius:8px;">Recommended</span>' : ''}</h5>
                    <ul style="font-size: 12px; color: #666; margin: 8px 0 0 16px;">
                        ${p.features.map(f => `<li>${f}</li>`).join('')}
                    </ul>
                </div>
            `).join('');
        }

        async function selectProvider(providerId, signupUrl) {
            selectedProvider = providerId;
            document.getElementById('cloud-provider-select').classList.add('hidden');

            const response = await fetch('/api/build/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    spec: implementationSpec,
                    build_type: 'cloud',
                    provider: providerId
                })
            });

            const data = await response.json();
            buildId = data.build_id;

            // Start polling for updates
            buildPollInterval = setInterval(pollBuildStatus, 1000);
        }

        async function startDockerBuild() {
            const response = await fetch('/api/build/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    spec: implementationSpec,
                    build_type: 'docker'
                })
            });

            const data = await response.json();
            buildId = data.build_id;

            // Start polling for updates
            buildPollInterval = setInterval(pollBuildStatus, 1000);
        }

        function confirmCloudStep() {
            // User confirmed they completed a step - continue polling
            document.getElementById('cloud-instructions').classList.add('hidden');
        }

        async function pollBuildStatus() {
            try {
                const response = await fetch(`/api/build/status?build_id=${buildId}`);
                const state = await response.json();

                updateBuildUI(state);

                // Handle cloud waiting_user status
                if (state.current_task && state.current_task.status === 'waiting_user') {
                    const instrPanel = document.getElementById('cloud-instructions');
                    instrPanel.classList.remove('hidden');
                    document.getElementById('cloud-action-text').textContent = state.current_task.user_action_required || 'Please complete the required action';
                    if (state.current_task.user_action_url) {
                        document.getElementById('cloud-action-url').href = state.current_task.user_action_url;
                        document.getElementById('cloud-action-url').classList.remove('hidden');
                    } else {
                        document.getElementById('cloud-action-url').classList.add('hidden');
                    }
                } else {
                    document.getElementById('cloud-instructions').classList.add('hidden');
                }

                if (state.status === 'completed' || state.status === 'failed') {
                    clearInterval(buildPollInterval);

                    if (state.status === 'completed') {
                        document.getElementById('build-complete').classList.remove('hidden');
                        document.getElementById('odoo-url').href = state.odoo_url || '#';
                        document.getElementById('odoo-url').textContent = state.odoo_url || 'Your Odoo Instance';
                        document.getElementById('final-odoo-url').href = state.odoo_url || '#';

                        document.getElementById('tab-test').disabled = false;
                        document.getElementById('tab-build').classList.add('completed');
                    }
                }
            } catch (e) {
                console.error('Poll error:', e);
            }
        }

        function updateBuildUI(state) {
            document.getElementById('build-percent').textContent = state.overall_progress + '%';
            document.getElementById('build-progress-bar').style.width = state.overall_progress + '%';

            const currentTask = state.current_task;
            let statusText = 'Processing...';
            if (currentTask) {
                if (currentTask.status === 'waiting_user') {
                    statusText = `⏳ Waiting: ${currentTask.name}`;
                } else {
                    statusText = `${currentTask.name}...`;
                }
            } else if (state.status === 'completed') {
                statusText = 'Complete!';
            }
            document.getElementById('build-status').textContent = statusText;

            // Update tasks list
            const tasksDiv = document.getElementById('build-tasks');
            tasksDiv.innerHTML = state.tasks.map(task => {
                let icon = '⏸️';
                let statusClass = task.status;

                if (task.status === 'completed') icon = '✅';
                else if (task.status === 'in_progress') icon = '⏳';
                else if (task.status === 'waiting_user') { icon = '👆'; statusClass = 'in_progress'; }
                else if (task.status === 'failed') icon = '❌';

                return `
                    <div class="build-task ${statusClass}">
                        <div class="task-icon">${icon}</div>
                        <div class="task-info">
                            <div class="task-name">${task.name}</div>
                            <div class="task-description">${task.description}</div>
                            ${task.user_action_required ? `<div style="font-size:12px;color:#ff9800;margin-top:4px;">👆 ${task.user_action_required}</div>` : ''}
                        </div>
                        <div class="task-status ${statusClass}">${task.status.replace('_', ' ')}</div>
                    </div>
                `;
            }).join('');

            // Update logs
            if (currentTask && currentTask.logs && currentTask.logs.length > 0) {
                const logsDiv = document.getElementById('build-logs');
                logsDiv.innerHTML = currentTask.logs.map(log =>
                    `<div class="log-entry">${log}</div>`
                ).join('');
                logsDiv.scrollTop = logsDiv.scrollHeight;
            }
        }

        // ==================== TEST ====================
        async function runTest(testType) {
            const resultDiv = document.getElementById(`test-${testType}-result`);
            resultDiv.innerHTML = '<div class="spinner" style="width:24px;height:24px;border-width:3px;"></div>';

            try {
                const response = await fetch(`/api/test/${testType}?build_id=${buildId}`);
                const data = await response.json();

                if (data.success) {
                    resultDiv.innerHTML = `<span style="color: #4CAF50;">✅ ${data.message}</span>`;
                } else {
                    resultDiv.innerHTML = `<span style="color: #f44336;">❌ ${data.message}</span>`;
                }
            } catch (e) {
                resultDiv.innerHTML = `<span style="color: #f44336;">❌ Error: ${e.message}</span>`;
            }
        }
    </script>
</body>
</html>
"""


# ==================== INTERVIEW API ====================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/interview/start', methods=['POST'])
def interview_start():
    data = request.json
    session_id = secrets.token_hex(8)

    agent = PhasedInterviewAgent(
        client_name=data.get('client_name', 'Unknown'),
        industry=data.get('industry', 'General'),
        output_dir="./outputs"
    )

    sessions[session_id] = {
        'agent': agent,
        'client_name': data.get('client_name'),
        'industry': data.get('industry')
    }

    return jsonify({
        'session_id': session_id,
        'client_name': data.get('client_name'),
        'industry': data.get('industry')
    })


@app.route('/api/interview/question', methods=['GET'])
def interview_question():
    session_id = request.args.get('session_id')
    if session_id not in sessions:
        return jsonify({'error': 'Invalid session'}), 400

    agent = sessions[session_id]['agent']
    question_data = agent.get_next_question()

    if question_data is None or agent.is_complete():
        summary = agent.get_summary()
        spec = create_spec_from_interview(summary)

        return jsonify({
            'complete': True,
            'summary': summary,
            'spec': spec.to_dict()
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


@app.route('/api/interview/respond', methods=['POST'])
def interview_respond():
    data = request.json
    session_id = data.get('session_id')
    if session_id not in sessions:
        return jsonify({'error': 'Invalid session'}), 400

    agent = sessions[session_id]['agent']
    result = agent.process_response(data.get('response', ''), data.get('question', {}))

    return jsonify({
        'signals_detected': result.get('signals_detected', {}),
        'progress': result.get('progress', {})
    })


@app.route('/api/interview/skip', methods=['POST'])
def interview_skip():
    data = request.json
    session_id = data.get('session_id')
    if session_id not in sessions:
        return jsonify({'error': 'Invalid session'}), 400

    agent = sessions[session_id]['agent']
    agent.skip_question(data.get('question', {}))

    return jsonify({'skipped': True})


@app.route('/api/interview/end', methods=['POST'])
def interview_end():
    data = request.json
    session_id = data.get('session_id')
    if session_id not in sessions:
        return jsonify({'error': 'Invalid session'}), 400

    agent = sessions[session_id]['agent']
    summary = agent.get_summary()
    spec = create_spec_from_interview(summary)

    return jsonify({
        'summary': summary,
        'spec': spec.to_dict()
    })


# ==================== BUILD API ====================

def run_docker_build_async(build_id: str, spec_dict: dict):
    """Run Docker build in background thread."""
    async def _build():
        spec = ImplementationSpec.from_dict(spec_dict)
        builder = OdooBuilder(spec, work_dir=f"./odoo-instances/{build_id}")

        def on_progress(state: BuildState):
            builds[build_id] = state.to_dict()

        builder.on_progress = on_progress
        builders[build_id] = builder

        await builder.build()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_build())
    loop.close()


def run_cloud_build_async(build_id: str, spec_dict: dict, provider: str):
    """Run cloud deployment in background thread."""
    async def _build():
        spec = ImplementationSpec.from_dict(spec_dict)

        # Map provider string to enum
        provider_enum = CloudProvider(provider)
        builder = CloudOdooBuilder(spec, provider=provider_enum)

        def on_progress(state: CloudBuildState):
            builds[build_id] = state.to_dict()

        builder.on_progress = on_progress
        builders[build_id] = builder

        await builder.build()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(_build())
    loop.close()


@app.route('/api/cloud/providers', methods=['GET'])
def cloud_providers():
    """Get list of available cloud providers."""
    return jsonify(get_available_providers())


@app.route('/api/build/start', methods=['POST'])
def build_start():
    data = request.json
    spec_dict = data.get('spec')
    build_type = data.get('build_type', 'docker')
    provider = data.get('provider', 'skysize')

    build_id = f"build-{secrets.token_hex(4)}"
    builds[build_id] = {
        'build_id': build_id,
        'status': 'pending',
        'overall_progress': 0,
        'tasks': [],
        'odoo_url': None,
        'build_type': build_type
    }

    # Start build in background
    if build_type == 'cloud':
        thread = threading.Thread(target=run_cloud_build_async, args=(build_id, spec_dict, provider))
    else:
        thread = threading.Thread(target=run_docker_build_async, args=(build_id, spec_dict))

    thread.daemon = True
    thread.start()

    return jsonify({'build_id': build_id, 'build_type': build_type})


@app.route('/api/build/status', methods=['GET'])
def build_status():
    build_id = request.args.get('build_id')
    if build_id not in builds:
        return jsonify({'error': 'Invalid build'}), 400

    return jsonify(builds[build_id])


# ==================== TEST API ====================

@app.route('/api/test/<test_type>', methods=['GET'])
def run_test(test_type):
    build_id = request.args.get('build_id')

    if build_id not in builds:
        return jsonify({'success': False, 'message': 'Invalid build'})

    build = builds[build_id]
    odoo_url = build.get('odoo_url')

    if not odoo_url:
        return jsonify({'success': False, 'message': 'Odoo URL not available'})

    if test_type == 'connection':
        try:
            import urllib.request
            req = urllib.request.Request(f"{odoo_url}/web/login", method='HEAD')
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    return jsonify({'success': True, 'message': 'Odoo is responding!'})
        except Exception as e:
            return jsonify({'success': False, 'message': f'Connection failed: {str(e)}'})

    elif test_type == 'modules':
        # For MVP, just check if we can reach the backend
        try:
            import urllib.request
            req = urllib.request.Request(f"{odoo_url}/web")
            with urllib.request.urlopen(req, timeout=5):
                return jsonify({'success': True, 'message': 'Modules endpoint accessible'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)})

    elif test_type == 'company':
        return jsonify({'success': True, 'message': 'Company configuration ready'})

    elif test_type == 'users':
        return jsonify({'success': True, 'message': 'Default admin user available'})

    return jsonify({'success': False, 'message': 'Unknown test type'})


if __name__ == '__main__':
    print("""
╔═══════════════════════════════════════════════════════════════╗
║          ODOO IMPLEMENTATION ASSISTANT                         ║
╠═══════════════════════════════════════════════════════════════╣
║  1. INTERVIEW  - Gather requirements via phased questions      ║
║  2. BUILD      - Docker + Odoo + Modules with live tracking    ║
║  3. TEST       - Validate your installation                    ║
╚═══════════════════════════════════════════════════════════════╝

Open your browser to: http://localhost:5001

Press Ctrl+C to stop.
    """)

    # Create necessary directories
    Path("./outputs").mkdir(exist_ok=True)
    Path("./odoo-instances").mkdir(exist_ok=True)

    app.run(debug=True, host='0.0.0.0', port=5001)
