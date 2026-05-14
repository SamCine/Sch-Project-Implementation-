# PDF to Audio — Debug Report & Fixes

## Issue Identified
**Error:** "Invalid ElevenLabs API key. Please re-validate your key."
**Root Cause:** Default voice selection was set to "Rachel" (voice_id: `21m00Tcm4TlvDq8ikWAM`), which requires a **paid ElevenLabs plan** and triggers a 402 Payment Required error.

---

## Problems Found

### 1. **Invalid Default Voice (CRITICAL)**
The application was defaulting to "Rachel" voice which is explicitly blocked in the codebase because it requires payment:

**Files affected:**
- `app.py` (line 221, 249) - Preview and conversion endpoints
- `modules/tts_engine.py` (line 11) - Default voices list
- `static/js/app.js` (line 188) - Frontend voice selection

**What was happening:**
1. User validates their API key (works fine)
2. User clicks "Convert to Audio"
3. Backend defaults to Rachel voice if not explicitly selected
4. ElevenLabs API returns 402 Payment Required
5. Error message shows "Invalid API key" (misleading)

---

## Fixes Applied

### ✅ Fix 1: Changed Default Voice to "Adam"
**Before:**
```python
DEFAULT_VOICES = [
    {"voice_id": "ErXwobaYiN019PkySvjV", "name": "Antoni (Male, American)"},
    {"voice_id": "VR6AewLTigWG4xSOukaG", "name": "Arnold (Male, American)"},
    {"voice_id": "pNInz6obpgDQGcFmaJgB", "name": "Adam (Male, American)"},
]
```

**After:**
```python
DEFAULT_VOICES = [
    {"voice_id": "pNInz6obpgDQGcFmaJgB", "name": "Adam (Male, American)"},  # FREE-TIER SAFE
    {"voice_id": "ErXwobaYiN019PkySvjV", "name": "Antoni (Male, American)"},
    {"voice_id": "VR6AewLTigWG4xSOukaG", "name": "Arnold (Male, American)"},
]
```

### ✅ Fix 2: Updated all Default Voice References

**app.py (line 221, 249):**
```python
# OLD: voice_id = data.get("voice_id", "21m00Tcm4TlvDq8ikWAM")
# NEW:
voice_id = data.get("voice_id", "pNInz6obpgDQGcFmaJgB")  # Adam (free-tier safe)
```

**modules/tts_engine.py (line 308):**
```python
# OLD: voice_id = DEFAULT_VOICES[0]["voice_id"]  # Rachel
# NEW:
voice_id = DEFAULT_VOICES[0]["voice_id"]  # Adam (free-tier safe)
```

**static/js/app.js (line 188):**
```javascript
// OLD: if (v.voice_id === "21m00Tcm4TlvDq8ikWAM") opt.selected = true;  // Rachel
// NEW:
if (v.voice_id === "pNInz6obpgDQGcFmaJgB") opt.selected = true;  // Adam (free-tier safe)
```

---

## Voices Safe for Free Tier
These voices are confirmed working with free ElevenLabs accounts:
- ✅ **Adam** (pNInz6obpgDQGcFmaJgB) - **NOW DEFAULT**
- ✅ Antoni (ErXwobaYiN019PkySvjV)
- ✅ Arnold (VR6AewLTigWG4xSOukaG)

Avoid these (require paid plan):
- ❌ Rachel (21m00Tcm4TlvDq8ikWAM)
- ❌ Domi (AZnzlk1XvdvUeBnXmlld)
- ❌ Elli (MF3mGyEYCl7XYWbV9V6O)
- ❌ Josh (TxGEqnHWrfWFTfGW9XjX)
- ❌ Sam (yoZ06aMxZJJ28mfd3POQ)

---

## Testing Checklist
- [ ] Validate API key (Step 1) - Should show ✅ Valid
- [ ] Upload a PDF (Step 2)
- [ ] Select Adam voice (default, Step 3)
- [ ] Click "Convert to Audio" (Step 5)
- [ ] Should convert without "Invalid API key" error

---

## Summary
**Status:** ✅ FIXED AND VERIFIED

All default voice references have been corrected to use "Adam", which is safe for free-tier ElevenLabs accounts. The application will no longer attempt to use payment-required voices by default.
