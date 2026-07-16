# Version Filtering Guide

Filter Memfault issues by firmware version to identify version-specific problems and regressions.

## Quick Start

```bash
python main.py
```

```
memfault> list
memfault> versions           # Show all firmware versions
memfault> filter-version 3.1.19 only
```

## Commands

### `versions`
Shows all firmware versions present in current issues with counts.

```
Firmware Versions (27 total):

  3.1.7+5a5c5903    - Only:   0 issues | Started:   1 issues
  3.1.19+388d82f0   - Only:   0 issues | Started:   0 issues
  4.0.4+36b17978    - Only:   1 issues | Started:   1 issues
```

**Columns:**
- **Only**: Issues that appear ONLY in this version (first_version == last_version)
- **Started**: Issues that first appeared in this version

### `filter-version <version> [mode]`
Filter issues by firmware version.

**Modes:**

#### 1. `only` (default)
Issues that **only occur** in this specific version.

```
memfault> filter-version 4.0.4+36b17978 only
# Shows issues exclusive to this version
```

**Use case:** Find version-specific bugs (likely introduced and fixed in this version)

#### 2. `started`
Issues that **first appeared** in this version.

```
memfault> filter-version 3.1.7+5a5c5903 started
# Shows regressions introduced in 3.1.7
```

**Use case:** Identify what broke in this release

#### 3. `present`
Issues **present** in this version (between first and last seen).

```
memfault> filter-version 3.1.19+388d82f0 present
# Shows all issues affecting this version
```

**Use case:** Know all issues affecting a deployed version

#### 4. `exclude`
Issues **NOT present** in this version.

```
memfault> filter-version 4.0.4+36b17978 exclude
# Shows issues not affecting this version
```

**Use case:** Find issues that were fixed before this version

#### 5. `clear`
Remove version filter.

```
memfault> filter-version clear
```

## Combining Filters

Version filtering works with other filters:

```bash
# Unresolved issues that started in 3.1.19
memfault> filter unresolved
memfault> filter-version 3.1.19+388d82f0 started
memfault> sort devices

# High-impact issues affecting 4.0.4
memfault> filter-version 4.0.4+36b17978 present
memfault> sort devices desc
```

## Common Workflows

### 1. Find Regressions in New Release

```
memfault> versions
# Note the new version: 4.0.5+7a440a11

memfault> filter-version 4.0.5+7a440a11 started
memfault> sort devices desc
# Shows new issues introduced in 4.0.5, sorted by impact
```

### 2. Validate a Fix

```
# Check if issue 1804744331 is fixed in 4.0.5
memfault> filter-version 4.0.5+7a440a11 exclude
# If the issue appears here, it's NOT in 4.0.5 (fixed!)
```

### 3. Pre-Release Testing Priority

```
# Before releasing 4.0.6, what issues should we test?
memfault> filter-version 4.0.6 present
memfault> sort devices desc
# Focus testing on these high-impact issues
```

### 4. Version Comparison

```
# What's different between 3.1.19 and 4.0.4?
memfault> filter-version 3.1.19 present
# Note the count

memfault> filter-version 4.0.4 present
# Compare counts - fewer issues = progress!
```

### 5. Find Persistent Issues

```
# Issues that have been around for many versions
memfault> list
# Look at issues where first_version != last_version
# These span multiple releases
```

## Examples

### Example 1: New Release Analysis

```
memfault> versions

Firmware Versions (27 total):
  ...
  4.0.4+36b17978    - Only:   1 issues | Started:   1 issues
  4.0.5+7a440a11    - Only:   0 issues | Started:   2 issues

memfault> filter-version 4.0.5+7a440a11 started
memfault> sort devices

                  Memfault Issues | version=4.0.5 (started)
┏━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┓
┃ #  ┃ ID         ┃ Title                    ┃ Status ┃ Devices ┃ Traces ┃
┡━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━┩
│ 1  │ 1805123456 │ Error at se050_init      │ open   │     234 │    567 │
│ 2  │ 1805123457 │ Assert at power_manager  │ open   │      89 │    123 │
└────┴────────────┴──────────────────────────┴────────┴─────────┴────────┘

Showing 2 of 20 issues

# These are regressions in 4.0.5!
```

### Example 2: Release Readiness

```
memfault> filter-version 4.0.6 present
memfault> sort devices desc

# Top 5 issues to test before releasing 4.0.6:
# 1. High device count issues
# 2. Recent regressions
# 3. Persistent bugs
```

### Example 3: Fix Validation

```
# We think issue 1804744331 was fixed in 3.1.20
memfault> analyze 1804744331

Issue Details: 1804744331
  First Software Version: 3.1.7+5a5c5903
  Last Software Version: 3.1.19+388d82f0

# Last seen in 3.1.19, so it's likely fixed in 3.1.20+
```

## Technical Details

### Version Matching

The filter uses string comparison on version strings:
```
first_version <= target_version <= last_version
```

**Works well when:**
- Versions are sequential (3.1.18, 3.1.19, 3.1.20)
- Semantic versioning is consistent

**Limitations:**
- Doesn't parse semantic version (treats as strings)
- Assumes sequential versioning
- Git hashes don't affect ordering

### Issue Version Fields

Each issue has:
```python
{
  "first_software_version": {
    "version": "3.1.7+5a5c5903",  # First time seen
    "software_type": "diamond-security-app"
  },
  "last_software_version": {
    "version": "3.1.19+388d82f0",  # Most recently seen
    "software_type": "diamond-security-app"
  }
}
```

### Filter Logic

```python
"only":    first_version == version AND last_version == version
"started": first_version == version
"present": first_version <= version <= last_version
"exclude": NOT (first_version <= version <= last_version)
```

## Integration with Autonomous Mode

Version filtering works with autonomous analysis:

```bash
# Analyze only regressions in latest release
memfault> filter-version 4.0.5+7a440a11 started
memfault> batch-analyze

# Attempt fixes for version-specific issues
memfault> filter-version 4.0.4+36b17978 only
memfault> auto-fix 3
```

## Tips

1. **Use `versions` first** - See what versions exist before filtering
2. **Combine with `sort devices`** - Focus on high-impact issues
3. **`started` for regressions** - New issues in new versions
4. **`present` for release testing** - All issues affecting a version
5. **`only` for quick fixes** - Version-specific bugs are often simple
6. **`exclude` for validation** - Confirm fixes worked

## Troubleshooting

**"No issues match the current filters"**
- The version string must match exactly (including git hash)
- Use `versions` to see exact version strings
- Try `started` or `present` instead of `only`

**"Version not found"**
- Check spelling with `versions` command
- Include full version with git hash: `3.1.19+388d82f0`

**Unexpected results**
- Remember: string comparison, not semantic versioning
- Check first_version and last_version in issue details
- Version must be exact match (case-sensitive)

## See Also

- [README.md](../../README.md) - Main documentation
- [AUTONOMOUS_MODE.md](AUTONOMOUS_MODE.md) - Autonomous fixes
- [TRACE_ENHANCEMENT.md](TRACE_ENHANCEMENT.md) - Thread analysis
