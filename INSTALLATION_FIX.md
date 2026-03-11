# CraftBot Installation Fix - Updated Installer Scripts

## What Was Fixed

The installation scripts have been updated to provide better error handling and clearer guidance. Here are the key improvements:

### 1. **Playwright Browser Installation** (`install.py`)
**Problem:** Playwright chromium installation was failing silently with unclear error messages.

**Solution:** 
- Better error handling that catches and reports failures clearly
- Installation continues even if Playwright fails (it's not critical for browser mode)
- Clear guidance on how to manually install Playwright if needed
- Shows first 300 chars of actual error for debugging

### 2. **Browser Frontend Setup** (`install.py`)
**Problem:** npm dependency installation had no feedback and failed with generic messages.

**Solution:**
- Checks if Node.js/npm is installed BEFORE trying to use it
- Detects if `node_modules` already exists to skip redundant installations
- Provides step-by-step installation instructions if npm is missing
- Better progress messages with clear troubleshooting steps

### 3. **Frontend Server Startup** (`run.py`)
**Problem:** Browser startup failed with generic error messages, users didn't know what to do.

**Solution:**
- Checks for Node.js availability before attempting to start
- Verifies frontend dependencies are installed
- Provides detailed troubleshooting guide when startup fails
- Clear links to Node.js downloads and manual installation steps

## How to Fix Your Current Issue

### Option 1: Re-run the Installer (Recommended)
The updated installer should now handle everything:

```bash
python install.py
```

This will:
1. ✓ Check/install core Python dependencies
2. ✓ Check if Node.js is available
3. ✓ Install frontend npm packages (if Node.js is found)
4. ✓ Attempt Playwright installation (but won't fail if it doesn't work)
5. ✓ Start CraftBot automatically

### Option 2: Manual Setup

If automatic installation doesn't work, manually install Node.js first:

1. **Install Node.js** (required for browser interface)
   - Download from: https://nodejs.org/
   - Choose LTS (Long-Term Support) version
   - Install and restart your terminal

2. **Verify Installation**
   ```bash
   node --version
   npm --version
   ```

3. **Install Frontend Dependencies**
   ```bash
   cd app/ui_layer/browser/frontend
   npm install
   ```

4. **Run CraftBot**
   ```bash
   python run.py
   ```

### Option 3: Skip Browser Mode (TUI Mode)

If you can't or don't want to use the browser interface:

```bash
python run.py --tui
```

This launches CraftBot in Terminal UI mode without needing Node.js/npm.

## Playwright Chromium Note

Playwright chromium is only needed for WhatsApp Web integration. It's optional for basic CraftBot functionality.

If you need it later, install manually:
```bash
playwright install chromium
```

## Key Improvements in Updated Scripts

### `install.py` improvements:
- ✓ Playwright installation errors are handled gracefully
- ✓ Non-critical failures don't stop the installation
- ✓ npm installation checks for Node.js availability first
- ✓ Better error messages guide users to solutions
- ✓ Skip npm install if node_modules already exists

### `run.py` improvements:
- ✓ Frontend startup checks all dependencies before attempting launch
- ✓ Detailed troubleshooting guide when frontend fails
- ✓ Clear instructions for installing Node.js
- ✓ Better error messages with actionable steps

## Still Having Issues?

If you still encounter problems:

1. **Check Python version**: `python --version` (need 3.10+)
2. **Check Node.js**: `node --version` (if using browser mode)
3. **Check npm**: `npm --version` (if using browser mode)
4. **Clear and reinstall**:
   ```bash
   cd app/ui_layer/browser/frontend
   rm -rf node_modules package-lock.json
   npm install
   ```

5. **Try TUI mode as fallback**:
   ```bash
   python run.py --tui
   ```

## Summary of Command Changes

- **Full installation with browser**: `python install.py`
- **Run browser mode**: `python run.py` (default)
- **Run TUI mode** (no browser needed): `python run.py --tui`
- **With conda** (if installed): `python install.py --conda`
- **With GUI mode**: `python install.py --gui` (requires additional setup)

The updated scripts will now guide you through any missing dependencies with clear, actionable instructions.
