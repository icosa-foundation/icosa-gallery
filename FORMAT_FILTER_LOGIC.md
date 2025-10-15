# Format Filter Exclusion Logic

## Overview

This document describes the format filter logic used in the Icosa Gallery API, specifically the exclusion behavior when using negative format filters (e.g., `-TILT`, `-BLOCKS`).

## Problem Statement

The original issue asked: What should `assets?format=GLTF2&format=-TILT` return?

**Option 1 (old behavior):** All assets that EITHER have GLTF2 OR have no TILT file
**Option 2 (new behavior):** All assets that have GLTF2 BUT have no TILT file

Option 2 is more useful and solves the use case: "I want all these formats but not if they have TILT files"

## Implementation

### Filter Logic Rules

1. **Get all the non-negative results** - OR positive formats together
2. **Exclude the negative results** - AND negative formats together as exclusions
3. **Combine them** - AND the positive and negative groups together

### Examples

#### Single Positive Format
```
format=GLTF2
→ Q(has_gltf2=True)
→ Returns: Assets with GLTF2
```

#### Multiple Positive Formats (OR logic)
```
format=GLTF2&format=OBJ
→ Q(has_gltf2=True) | Q(has_obj=True)
→ Returns: Assets with GLTF2 OR OBJ
```

#### Single Negative Format
```
format=-TILT
→ Q(has_tilt=False)
→ Returns: Assets without TILT
```

#### Multiple Negative Formats (AND logic)
```
format=-TILT&format=-BLOCKS
→ Q(has_tilt=False) & Q(has_blocks=False)
→ Returns: Assets without TILT AND without BLOCKS
```

#### Mixed Positive and Negative
```
format=GLTF2&format=-TILT
→ Q(has_gltf2=True) & Q(has_tilt=False)
→ Returns: Assets with GLTF2 AND without TILT
```

#### Complex Query
```
format=GLTF2&format=OBJ&format=-TILT&format=-BLOCKS
→ (Q(has_gltf2=True) | Q(has_obj=True)) & Q(has_tilt=False) & Q(has_blocks=False)
→ Returns: Assets with (GLTF2 OR OBJ) that don't have TILT or BLOCKS
```

## Rationale

### Why OR for Positive Formats?

When requesting multiple positive formats, users typically want assets that have ANY of those formats. For example:
- `format=GLTF2&format=OBJ` means "give me assets I can use in either GLTF2 or OBJ format"

### Why AND for Negative Formats?

When excluding multiple formats, users want to exclude assets that have ANY of those formats. This is accomplished by requiring ALL exclusion conditions to be true:
- `format=-TILT&format=-BLOCKS` means "exclude assets that have TILT AND exclude assets that have BLOCKS"
- This is equivalent to: "give me assets that have neither TILT nor BLOCKS"

Using OR for negative formats would give the opposite behavior:
- `Q(has_tilt=False) | Q(has_blocks=False)` would match assets that lack EITHER format
- This would match almost all assets (anything missing at least one format)

### Why AND Between Positive and Negative?

When combining positive and negative filters, users want to:
1. First, filter to assets that match the requested formats (positive filters ORed)
2. Then, exclude assets with unwanted formats (negative filters ANDed)

This matches the intuitive expectation: "I want GLTF2 files, but not if they also have TILT"

## Implementation Details

The logic is implemented in `django/icosa/api/filters.py` in the `filter_format` method:

```python
def filter_format(self, value: List[FilterFormat]) -> Q:
    q = Q()
    if value:
        positive_q = Q()
        negative_q = Q()
        has_positive = False
        has_negative = False
        
        for format in value:
            format_value = format.value
            # Handle GLTF special case
            if format == FilterFormat.GLTF:
                format_value = "GLTF_ANY"
            if format == FilterFormat.NO_GLTF:
                format_value = "-GLTF_ANY"
            
            if format_value.startswith("-"):
                # Negative formats: AND them together
                negative_q &= Q(**{f"has_{format_value.lower()[1:]}": False})
                has_negative = True
            else:
                # Positive formats: OR them together
                positive_q |= Q(**{f"has_{format_value.lower()}": True})
                has_positive = True
        
        # Combine positive and negative queries with AND
        if has_positive and has_negative:
            q = positive_q & negative_q
        elif has_positive:
            q = positive_q
        elif has_negative:
            q = negative_q
            
    return q
```

## Testing

Tests are located in `django/icosa/test_filters.py` and cover:
- Single positive format
- Multiple positive formats (OR behavior)
- Single negative format
- Multiple negative formats (AND behavior)
- Mixed positive and negative formats
- Complex queries with multiple formats of each type

## Database Fields

The filter relies on denormalized boolean fields in the Asset model:
- `has_tilt`
- `has_blocks`
- `has_gltf1`
- `has_gltf2`
- `has_gltf_any` (matches either GLTF1 or GLTF2)
- `has_fbx`
- `has_obj`

These fields are automatically updated when asset formats change (see `Asset.denorm_format_types()` method).
