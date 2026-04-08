# Integration Test Report

## 01 — Read File

**Method**: `vault.read_file("note.md")`
**Result**: PASS

### Before (`note.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### After (`note.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### Returned Value
```text
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

## 02 — Write File (New)

**Method**: `vault.write_file("new-file.md", content)`
**Result**: PASS

### Before (`listing.txt`)
```text
.hidden/secret.md
Projects/Alpha.md
Projects/Beta.md
_hidden_dir/internal.md
existing.md
large-file.md
note.md
to-delete.md
```

### After (`new-file.md`)
```markdown
# New File

Created by integration test.
```

## 03 — Write File (Overwrite)

**Method**: `vault.write_file("existing.md", "New content here.\n")`
**Result**: PASS

### Before (`existing.md`)
```markdown
---
title: Existing File
---

Original content that will be overwritten.
```

### After (`existing.md`)
```markdown
New content here.
```

## 04 — Write Nested New

**Method**: `vault.write_file("Deep/Nested/new.md", content)`
**Result**: PASS

### Before (`listing.txt`)
```text
.hidden/secret.md
Projects/Alpha.md
Projects/Beta.md
_hidden_dir/internal.md
existing.md
large-file.md
new-file.md
note.md
to-delete.md
```

### After (`Deep/Nested/new.md`)
```markdown
# Deep Note

Nested content.
```

## 05 — Delete File

**Method**: `vault.delete_file("to-delete.md")`
**Result**: PASS

### Before (`to-delete.md`)
```markdown
# Delete Me

This file should be deleted.
```

## 06 — List Files (Default)

**Method**: `vault.list_files()`
**Result**: PASS

### Returned Value
```text
Deep/Nested/new.md
Projects/Alpha.md
Projects/Beta.md
existing.md
large-file.md
new-file.md
note.md
```

## 07 — List Files (Glob)

**Method**: `vault.list_files("Projects/*.md")`
**Result**: PASS

### Returned Value
```text
Projects/Alpha.md
Projects/Beta.md
```

## 08 — Search Files

**Method**: `vault.search_files("sprint")`
**Result**: PASS

### Returned Value
```text
note.md: se
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the
```

## 09 — Get Frontmatter

**Method**: `vault.get_frontmatter("fm-get.md")`
**Result**: PASS

### Before (`fm-get.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### After (`fm-get.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### Returned Value
```text
{'title': 'Meeting Notes', 'tags': ['work', 'weekly'], 'status': 'draft', 'priority': 'high', 'metadata': {'author': 'Jane', 'reviewed': False}}
```

## 10 — Set Frontmatter

**Method**: `vault.set_frontmatter("fm-set.md", {"title": "Replaced", "new_field": true})`
**Result**: PASS

### Before (`fm-set.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### After (`fm-set.md`)
```markdown
---
title: Replaced
new_field: true
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

## 11 — Update Frontmatter (Merge)

**Method**: `vault.update_frontmatter("fm-merge.md", {"status": "published", "reviewer": "Bob"})`
**Result**: PASS

### Before (`fm-merge.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### After (`fm-merge.md`)
```markdown
---
title: Meeting Notes
tags:
- work
- weekly
status: published
priority: high
metadata:
  author: Jane
  reviewed: false
reviewer: Bob
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

## 12 — Update Frontmatter (Shallow)

**Method**: `vault.update_frontmatter("fm-shallow.md", {"metadata": {"author": "New"}})`
**Result**: PASS

### Before (`fm-shallow.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### After (`fm-shallow.md`)
```markdown
---
title: Meeting Notes
tags:
- work
- weekly
status: draft
priority: high
metadata:
  author: New
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

## 13 — Update Frontmatter (Creates)

**Method**: `vault.update_frontmatter("no-fm.md", {"title": "Added"})`
**Result**: PASS

### Before (`no-fm.md`)
```markdown
# No Frontmatter

Body stays here.
```

### After (`no-fm.md`)
```markdown
---
title: Added
---
# No Frontmatter

Body stays here.
```

## 14 — Delete Frontmatter Field

**Method**: `vault.delete_frontmatter_field("fm-delete.md", "priority")`
**Result**: PASS

### Before (`fm-delete.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### After (`fm-delete.md`)
```markdown
---
title: Meeting Notes
tags:
- work
- weekly
status: draft
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

## 15 — Delete Frontmatter Field (No-op)

**Method**: `vault.delete_frontmatter_field("fm-noop.md", "nonexistent")`
**Result**: PASS

### Before (`fm-noop.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### After (`fm-noop.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

## 16 — Read Heading

**Method**: `vault.read_heading("cp-heading.md", "## Agenda")`
**Result**: PASS

### Before (`cp-heading.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### After (`cp-heading.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### Returned Value
```text

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review
```

## 17 — Write Heading (Replace)

**Method**: `vault.write_heading("cp-heading.md", "## Notes", "Replaced notes.\n")`
**Result**: PASS

### Before (`cp-heading.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### After (`cp-heading.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes
Replaced notes.
## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

## 18 — Write Heading (Append)

**Method**: `vault.write_heading("cp-append.md", "## New Section", "Appended content.\n")`
**Result**: PASS

### Before (`cp-append.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### After (`cp-append.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item

## New Section
Appended content.
```

## 19 — Read Block

**Method**: `vault.read_block("cp-block.md", "^meeting-notes")`
**Result**: PASS

### Before (`cp-block.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### After (`cp-block.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### Returned Value
```text
Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes
```

## 20 — Write Block

**Method**: `vault.write_block("cp-block.md", "^ref-block", "Updated reference paragraph. ^ref-block\n")`
**Result**: PASS

### Before (`cp-block.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### After (`cp-block.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Updated reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

## 21 — Write Block (List Item)

**Method**: `vault.write_block("cp-list.md", "^list-ref", "- Updated action item ^list-ref\n")`
**Result**: PASS

### Before (`cp-list.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Important action item ^list-ref
- Third item
```

### After (`cp-list.md`)
```markdown
---
title: Meeting Notes
tags: [work, weekly]
status: draft
priority: high
metadata:
  author: Jane
  reviewed: false
---

# Meeting Notes

Weekly sync for the product team.

## Agenda

- Review sprint progress
- Discuss blockers
- Plan next sprint

### Action Items

1. Update the roadmap
2. Schedule design review

## Notes

Key discussion points from the meeting.
The team agreed on the new timeline. ^meeting-notes

## References

- See also: [[Project Plan]]
- Related: [[Sprint Board]]

Some reference paragraph. ^ref-block

- First item
- Updated action item ^list-ref
- Third item
```

## 22 — Error: Path Escape

**Method**: `vault.read_file("../../etc/passwd")`
**Result**: PASS (raised PathError)

### Exception
```text
PathError: path traversal is not allowed
```

## 23 — Error: Absolute Path

**Method**: `vault.read_file("/etc/passwd")`
**Result**: PASS (raised PathError)

### Exception
```text
PathError: absolute paths are not allowed
```

## 24 — Error: Empty Path

**Method**: `vault.read_file("")`
**Result**: PASS (raised PathError)

### Exception
```text
PathError: path cannot be empty
```

## 25 — Error: Missing File

**Method**: `vault.read_file("nonexistent.md")`
**Result**: PASS (raised FileNotFoundError)

### Exception
```text
FileNotFoundError: nonexistent.md
```

## 26 — Error: File Too Large

**Method**: `vault.read_file("large-file.md")`
**Result**: PASS (raised FileTooLargeError)

### Exception
```text
FileTooLargeError: file exceeds max read size: large-file.md
```

## 27 — Error: Block Not Found

**Method**: `vault.write_block("note.md", "^missing", "x")`
**Result**: PASS (raised ContentPatchError)

### Exception
```text
ContentPatchError: block reference not found: ^missing
```

## 28 — Error: Malformed Frontmatter

**Method**: `vault.get_frontmatter("bad-yaml.md")`
**Result**: PASS (raised FrontmatterError)

### Exception
```text
FrontmatterError: invalid frontmatter YAML
```

## 29 — Is Busy

**Method**: `vault.is_busy()`
**Result**: PASS

### Returned Value
```text
False
```
