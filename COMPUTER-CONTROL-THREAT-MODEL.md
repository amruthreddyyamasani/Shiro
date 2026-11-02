# SHIRO — Desktop Control Threat Model & Safety Specifications

**Classification:** Safety Architecture & Adversarial Threat Analysis
**Scope:** Local Windows 11 Desktop Automation & Input Actuation
**Methodology:** STRIDE (Spoofing, Tampering, Repudiation, Information Disclosure, Denial of Service, Elevation of Privilege)

---

## 1. Threat Landscape & Boundary Definition

Allowing an AI agent to issue mouse and keyboard events on an active Windows desktop creates critical security risks if unconstrained. Unlike sandboxed file operations, desktop input operates with the security context of the logged-in user.

### Trust Boundaries
1. **User Trust Zone:** The human user sitting at the physical keyboard/mouse. The user retains absolute priority over all agent activity.
2. **Approved Application Boundary:** Only processes explicitly whitelisted by the user (e.g., `notepad.exe`, a designated browser tab, internal testing apps) may receive input.
3. **System & Security Boundary:** Protected OS windows (User Account Control dialogs, Task Manager, Windows Security, credential prompts, password managers) are **STRICTLY EXCLUDED** from observation and automation.

---

## 2. STRIDE Analysis & Security Mitigations

| Threat Category | Specific Attack Vector / Failure Mode | Mitigations Implemented in SHIRO |
| :--- | :--- | :--- |
| **Spoofing** | Attacker or malicious webpage spoofs an approved window title to redirect agent clicks. | Match targets by **Process ID (PID) + Executable Path Hash + HWND**, not solely window title text. Verify digital signature where applicable. |
| **Tampering** | Phishing prompt injected into a text file or web page instructs SHIRO to click a malicious link or run PowerShell commands. | 1. **Prohibit Arbitrary Shell/PowerShell execution** completely.<br>2. Restrict keyboard input to sanitized text (no raw key combination sequences like `Win+R -> cmd.exe`).<br>3. Consequential actions (Buy, Submit, Delete, Send) mandate explicit human approval tokens. |
| **Repudiation** | Actions performed on behalf of the user cannot be verified or traced after the fact. | **Immutable Audit Log:** Every mouse click (with x, y coordinates and target element automation ID) and keypress sequence is recorded to SQLite WAL `tool_audit` table with timestamp and optional snapshot thumbnail. |
| **Information Disclosure** | Background screen capture records confidential emails, banking tabs, or password manager vaults. | 1. **No Background Surveillance:** Screenshots are triggered solely during an active, explicit task step.<br>2. **Window-Only Cropping:** Full-screen capture is disallowed; images are cropped strictly to the target window rect.<br>3. **Sensitive App Blacklist:** Windows Security, Bitwarden, 1Password, KeePass, Credential Manager, and UAC are completely shielded. |
| **Denial of Service** | Agent enters an infinite typing or clicking loop, locking out user input. | 1. **Physical Failsafe:** Mouse movement to any screen corner immediately raises an uncatchable exception.<br>2. **Global Panic Hook:** `Ctrl+Alt+Escape` hardware hook immediately kills the action executor worker thread.<br>3. **Rate & Step Caps:** Maximum 15 desktop actions per task, minimum 250ms spacing between events. |
| **Elevation of Privilege** | Agent interacts with elevated (Admin) windows or clicks "Yes" on Windows UAC prompts. | 1. **Run as Standard User:** SHIRO runs under the standard user token without UI Access (`uiAccess=false`). Windows UAC dialogs render on a secure desktop that standard user apps cannot view or click.<br>2. Reject any window belonging to elevated processes. |

---

## 3. High-Risk Action Taxonomy & Approval Tiers

Every desktop action is mapped to a strict permission tier:

```
                      ┌────────────────────────────────────────┐
                      │        Action Requested by Plan        │
                      └───────────────────┬────────────────────┘
                                          │
            ┌─────────────────────────────┼─────────────────────────────┐
            ▼                             ▼                             ▼
       [TIER 0: SAFE]             [TIER 1: CONTROLLED]         [TIER 2: CONSEQUENTIAL]
   - List visible windows       - Focus approved window       - Close application (Alt+F4)
   - Inspect element tree       - Click button inside app     - Overwrite / Save As dialog
   - Capture target window rect - Type in designated field    - Click "Send", "Buy", "Delete"
            │                             │                             │
   (Automatic Execution)         (Allowlisted PID Check)       (Mandatory Human Approval)
```

### Tier 2 Mandatory Consequential Triggers
The action supervisor MUST halt and generate a `tool_approvals` record before executing:
1. Any click on an element containing text: `Delete`, `Remove`, `Submit`, `Send`, `Pay`, `Buy`, `Order`, `Confirm`, `Format`, `Uninstall`.
2. Any keystroke containing `Ctrl+S`, `Ctrl+W`, `Alt+F4`, or `Enter` inside a dialog or modal.
3. Switching focus to a new application that was not part of the initial task authorization.

---

## 4. Protected Windows Blacklist

The following applications and window classes are permanently blocked from discovery, capture, and interaction:

* `Windows.UI.Core.CoreWindow` (System shell, Start menu, Action Center)
* `CredentialUIBroker.exe` / `Consent.exe` (Windows Authentication & UAC)
* `taskmgr.exe` (Windows Task Manager)
* `cmd.exe` / `powershell.exe` / `pwsh.exe` / `wt.exe` (Command line terminals)
* `regedit.exe` (Registry Editor)
* KeePass, 1Password, Bitwarden, LastPass, Dashlane
* Any window marked with `WS_EX_TOPMOST` containing password input elements (`IsPassword=True` in UIA)

---

## 5. Visual Signal & Transparency Requirement

While computer control is active:
1. **Frontend Indication:** The SHIRO web UI displays an animated active status banner:
   `🔴 CONTROLLING DESKTOP: [App Name] (PID: 1234) — Press Esc or Move Mouse to Corner to Cancel`.
2. **Desktop Border (Future Overlay):** A subtle colored border (cyan/amber) is drawn around the target application window using a transparent GDI overlay window to provide instant physical feedback of what SHIRO is targeting.
