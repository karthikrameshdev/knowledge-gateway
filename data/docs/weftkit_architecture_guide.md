# WeftKit Desktop Architecture Guide

## Overview
WeftKit is a cross-platform desktop AI platform engineered with Tauri, Rust, and Vite/React.
It enables local-first workflows while securely bridging with cloud AI reasoning nodes.

## Core Architectural Layers
1. **Frontend Renderer (Vite + React + Tailwind)**:
   - Houses the user interface, session view, workspace browser, and chat canvas.
   - Communicates with the native backend strictly through Tauri IPC channels.
2. **Native Tauri Rust Core**:
   - Manages OS keychain secrets, local SQLite caching, file system watches, and child process execution.
3. **Knowledge Gateway Bridge**:
   - Resolves context items through the centralized Knowledge Gateway, fetching aggregated intelligence across RAG, OKF, Git, and PostgreSQL.
