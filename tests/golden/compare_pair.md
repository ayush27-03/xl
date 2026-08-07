# Comparison Report

Rows aligned on key 'Emp_ID' (confidence 0.6).

## Key findings

> **Integrity** - 1 column(s) changed type AND differ across rows - verify these are real changes, not a shift or formatting artifact: DoB (date->text, 1/3 rows changed).

- 1 column(s) dropped in the right table: ExitReason.
- 1 column(s) added in the right table: Bonus.
- Roster changed: 1 row(s) added, 1 removed (new / departed records).
- 1 column(s) changed in every one of the 3 matched rows (a systematic change, e.g. a revised run): Salary (e.g. Salary: 200 -> 220, +10.0%).
- 3 of 3 matched rows changed; 5 cell difference(s) across 3 column(s).
- Most-changed columns (by rows affected): Salary (3), City (1), DoB (1).
- Largest single numeric change: Salary 400 -> 440 (delta +40.0, +10.0%).

## Structural changes

| Change | Columns |
| --- | --- |
| Added | Bonus |
| Removed | ExitReason |
| Type changed | DoB (date -> text) |

## Record changes

Changed: 3; unchanged: 0; added: 1; removed: 1.

## Changed values

| Record | Column | Before | After | Delta | % change |
| --- | --- | --- | --- | --- | --- |
| 2 | Salary | 200 | 220 | +20.0 | +10.0% |
| 3 | Salary | 300 | 330 | +30.0 | +10.0% |
| 3 | City | Rome | Turin |  |  |
| 3 | DoB | 1992-03-03T00:00:00 | 1991-02-02 |  |  |
| 4 | Salary | 400 | 440 | +40.0 | +10.0% |

## Datasets

- Left: Pay!A1:F5 - 4 rows x 6 columns
- Right: Pay!A1:F5 - 4 rows x 6 columns

## Warnings & notes

- columns-only-in-left: 1 column(s) only in the left dataset: ['ExitReason'].
- columns-only-in-right: 1 column(s) only in the right dataset: ['Bonus'].
- row-key: Rows aligned on key 'Emp_ID': 3 matched, 1 only-left, 1 only-right (key overlap 0.6).
- column-retyped: Column 'DoB' changed type date -> text.
