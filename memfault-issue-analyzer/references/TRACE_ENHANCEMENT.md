# Thread and Stack Trace Enhancement

## Problem Identified

Issue 1804744331 (and all other issues) were missing critical debugging information:
- **Thread information** - Which thread crashed?
- **Stack traces** - Full call stack for each thread
- **Registers** - CPU register state at time of fault
- **Fault details** - Hardware fault registers and notes

This context is **essential** for firmware debugging but wasn't being fetched from Memfault.

## Root Cause

The Memfault API structure is:
```
Issues → Coredumps → Traces → Detailed Data (threads, stacks, registers)
```

We were only fetching the issue metadata, not the detailed trace data that contains thread information.

## Solution Implemented

### 1. Enhanced API Client (`memfault_client.py`)

**Changed from:**
- Trying non-existent `/issues/{id}/traces` endpoint
- Returning empty results

**Changed to:**
- Fetch coredumps via `/coredumps?issue_id={id}`
- For each coredump, get detailed trace via `/traces/{trace_id}`
- Return complete trace data with threads, stacks, and registers

```python
def get_issue_traces(self, issue_id: str, limit: int = 5) -> List[Dict]:
    # Get coredumps for this issue
    coredumps = fetch_coredumps(issue_id)

    # For each coredump, fetch detailed trace
    traces = []
    for coredump in coredumps:
        trace_id = coredump['trace_id']
        trace_details = fetch_trace(trace_id)  # Contains threads!
        traces.append(trace_details)

    return traces
```

### 2. Enhanced UI Display (`ui.py`)

Now shows:

**For each trace:**
- Device serial number
- Capture timestamp
- Fault reason and title

**Threads (up to 3 shown per trace):**
- Thread ID and name
- State (running, blocked, starting, etc.)
- **CRASHED** and **CURRENT** markers
- Full stack trace with function names and source locations
- Key registers (PC, LR, SP, R0-R3)

**Fault Information:**
- Fault notes (e.g., "Invalid instruction executed")
- Fault registers (CFSR, HFSR, SHCSR)

### 3. Enhanced Claude Analysis (`claude_analyzer.py`)

Claude now receives:

```markdown
## Detailed Trace Analysis (2 traces)

### Trace 1
- Captured: 2026-02-04T12:44:27
- Device: 0000
- Reason: Assert
- Title: Assert at timeout_default_handler

#### Fault Information
**Notes**:
  - Assert was triggered by software

**Fault Registers**:
  - CFSR: 0x00000000 (0)
  - HFSR: 0x00000000 (0)

#### Threads (16 threads)

**Thread 2: heartbeat**
  - State: running
  - Status: **CURRENT**
  - Key Registers:
      pc: 0x00000000 = 0x0
      lr: 0x0801d9dd = 134314461
      sp: 0x20012988 = 0x20012988
  - Stack Trace (32 frames):
      0x801d9f8: timeout_default_handler at src/timeouts.c:123
      0x801d9de: timeout_check at src/timeouts.c:98
      0x8025d4e: thread_main at src/threads/heartbeat.c:456
      ...
```

This gives Claude complete context about:
- Which thread had the problem
- Where in the call stack it occurred
- Register state at time of crash
- Hardware fault details

## Example Output

```
Trace Analysis (20 traces examined):

Trace #1:
  Device: 0000
  Captured: 2026-02-04T12:44:27.167000+00:00
  Reason: Assert
  Title: Assert at timeout_default_handler

  Threads (16 found):
    Thread 2: heartbeat (running) CURRENT
      Stack (showing top 5 frames):
        0x801d9f8: timeout_default_handler at src/timeouts.c:123
        0x801d9de: timeout_check at src/timeouts.c:98
        0x8025d4e: thread_main at src/threads/heartbeat.c:456
        0x8025d80: k_thread_entry at kernel/thread.c:234
        0x80124b0: z_thread_entry at kernel/init.c:567

    Thread 3: battery (starting)
    Thread 4: can_isotp_rx (blocked)

  Fault Notes:
    • Assert was triggered by software
```

## Impact on Analysis Quality

### Before Enhancement
Claude would see:
```
- Issue: Assert at app_assert_soft_handler
- Message: err 13
- 641 devices affected
```

**Analysis quality:** Limited - no context about where error occurred

### After Enhancement
Claude sees:
```
- Issue details
- Thread that crashed (heartbeat)
- Complete call stack showing function flow
- Register state
- Hardware fault details
- Multiple sample traces for pattern analysis
```

**Analysis quality:** High - complete debugging context

## Testing

```bash
python main.py
```

```
memfault> analyze 1804744331
```

You should now see:
- ✅ Full thread list with states
- ✅ Crashed/current thread markers
- ✅ Stack traces with function names
- ✅ Source file locations (if symbols available)
- ✅ Fault registers and notes

## What This Enables

### Better Root Cause Analysis
- Claude can see which thread crashed
- Can trace the exact call path to failure
- Can identify race conditions between threads
- Can spot stack overflow or corruption patterns

### More Accurate Fixes
- Specific function and line numbers for fixes
- Thread synchronization issues identified
- Proper context for ISR vs thread context bugs

### Pattern Recognition
- Compare stack traces across multiple devices
- Identify common failure paths
- Spot firmware version correlations

## Files Modified

1. **memfault_client.py**
   - Changed `get_issue_traces()` to use coredumps endpoint
   - Added trace detail fetching by trace_id
   - Returns complete trace objects with threads

2. **ui.py**
   - Added detailed thread display
   - Shows stack traces with formatting
   - Highlights crashed/current threads
   - Displays fault registers and notes

3. **claude_analyzer.py**
   - Enhanced `_format_issue_context()` to include threads
   - Formats stack traces for Claude
   - Includes register state
   - Shows fault details

## Verification

To verify this works for your issues:

```bash
# Test with the issue you mentioned
python main.py
> analyze 1804744331

# Should show:
# ✅ Trace Analysis (20 traces examined)
# ✅ Threads (16 found)
# ✅ Thread 2: heartbeat (running) CURRENT
# ✅ Stack (showing top 5 frames)
# ✅ Fault Notes
```

## Next Steps

Now that thread information is available:

1. **Batch analyze** will capture threads for all issues
2. **Claude's analysis** will be much more accurate
3. **Autonomous fixes** will target the right functions
4. **Pattern detection** can identify systemic threading issues

Run `batch-analyze` to re-analyze all issues with the enhanced context!
