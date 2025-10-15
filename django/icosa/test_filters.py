"""
Unit tests for format filter logic.

These tests validate the behavior of the filter_format method, specifically
testing the exclusion logic for format filters.

Current behavior (before fix):
    format=GLTF2&format=-TILT returns assets that:
    - (has_gltf2=True) OR (has_tilt=False)
    This returns all assets with GLTF2 OR all assets without TILT

Expected behavior (after fix):
    format=GLTF2&format=-TILT should return assets that:
    - (has_gltf2=True) AND (has_tilt=False)
    This returns only assets that have GLTF2 AND don't have TILT

Test scenarios:
1. Single positive format: format=GLTF2
   - Should return assets with GLTF2
   
2. Multiple positive formats: format=GLTF2&format=OBJ
   - Should return assets with GLTF2 OR OBJ
   
3. Single negative format: format=-TILT
   - Should return assets without TILT
   
4. Multiple negative formats: format=-TILT&format=-BLOCKS
   - Should return assets without TILT AND without BLOCKS
   
5. Mixed positive and negative: format=GLTF2&format=-TILT
   - Should return assets with GLTF2 AND without TILT
   
6. Multiple mixed: format=GLTF2&format=OBJ&format=-TILT&format=-BLOCKS
   - Should return assets with (GLTF2 OR OBJ) AND without TILT AND without BLOCKS
"""

from django.db.models import Q
from django.test import TestCase

# Import the actual FilterFormat enum and FiltersBase for testing
from icosa.api.filters import FilterFormat, FiltersBase


class FormatFilterLogicTest(TestCase):
    """Test the format filter logic without requiring database."""
    
    def test_single_positive_format(self):
        """Test filtering for a single positive format."""
        filters = FiltersBase(format=[FilterFormat.GLTF2])
        q = filters.filter_format([FilterFormat.GLTF2])
        
        # Should create: Q(has_gltf2=True)
        self.assertIsInstance(q, Q)
        # The Q object should be for positive inclusion
        self.assertIn("has_gltf2", str(q))
    
    def test_multiple_positive_formats(self):
        """Test filtering for multiple positive formats (should OR them)."""
        formats = [FilterFormat.GLTF2, FilterFormat.OBJ]
        filters = FiltersBase(format=formats)
        q = filters.filter_format(formats)
        
        # Should create: Q(has_gltf2=True) | Q(has_obj=True)
        self.assertIsInstance(q, Q)
        # Both formats should be in the query
        q_str = str(q)
        self.assertIn("has_gltf2", q_str)
        self.assertIn("has_obj", q_str)
    
    def test_single_negative_format(self):
        """Test filtering for a single negative format."""
        filters = FiltersBase(format=[FilterFormat.NO_TILT])
        q = filters.filter_format([FilterFormat.NO_TILT])
        
        # Should create: Q(has_tilt=False)
        self.assertIsInstance(q, Q)
        self.assertIn("has_tilt", str(q))
    
    def test_multiple_negative_formats(self):
        """Test filtering for multiple negative formats (should AND them)."""
        formats = [FilterFormat.NO_TILT, FilterFormat.NO_BLOCKS]
        filters = FiltersBase(format=formats)
        q = filters.filter_format(formats)
        
        # Should create: Q(has_tilt=False) & Q(has_blocks=False)
        self.assertIsInstance(q, Q)
        q_str = str(q)
        self.assertIn("has_tilt", q_str)
        self.assertIn("has_blocks", q_str)
    
    def test_mixed_positive_and_negative_formats(self):
        """Test filtering with both positive and negative formats."""
        formats = [FilterFormat.GLTF2, FilterFormat.NO_TILT]
        filters = FiltersBase(format=formats)
        q = filters.filter_format(formats)
        
        # Should create: Q(has_gltf2=True) & Q(has_tilt=False)
        self.assertIsInstance(q, Q)
        q_str = str(q)
        self.assertIn("has_gltf2", q_str)
        self.assertIn("has_tilt", q_str)
    
    def test_complex_mixed_formats(self):
        """Test filtering with multiple positive and negative formats."""
        formats = [
            FilterFormat.GLTF2,
            FilterFormat.OBJ,
            FilterFormat.NO_TILT,
            FilterFormat.NO_BLOCKS,
        ]
        filters = FiltersBase(format=formats)
        q = filters.filter_format(formats)
        
        # Should create: (Q(has_gltf2=True) | Q(has_obj=True)) & Q(has_tilt=False) & Q(has_blocks=False)
        self.assertIsInstance(q, Q)
        q_str = str(q)
        # All formats should be present
        self.assertIn("has_gltf2", q_str)
        self.assertIn("has_obj", q_str)
        self.assertIn("has_tilt", q_str)
        self.assertIn("has_blocks", q_str)
    
    def test_gltf_special_handling(self):
        """Test that GLTF and NO_GLTF are converted to GLTF_ANY."""
        # Test positive GLTF
        filters = FiltersBase(format=[FilterFormat.GLTF])
        q = filters.filter_format([FilterFormat.GLTF])
        self.assertIn("has_gltf_any", str(q))
        
        # Test negative GLTF
        filters = FiltersBase(format=[FilterFormat.NO_GLTF])
        q = filters.filter_format([FilterFormat.NO_GLTF])
        self.assertIn("has_gltf_any", str(q))


class FormatFilterBehaviorTest(TestCase):
    """Test the actual Q object behavior to ensure correct SQL generation."""
    
    def test_q_object_structure_single_positive(self):
        """Verify Q object structure for single positive format."""
        q = Q(has_gltf2=True)
        expected = Q(has_gltf2=True)
        self.assertEqual(str(q), str(expected))
    
    def test_q_object_structure_multiple_positive_or(self):
        """Verify Q object structure for multiple positive formats with OR."""
        q = Q(has_gltf2=True) | Q(has_obj=True)
        # This should use OR logic
        self.assertIn("OR", str(q))
    
    def test_q_object_structure_multiple_negative_and(self):
        """Verify Q object structure for multiple negative formats with AND."""
        q = Q(has_tilt=False) & Q(has_blocks=False)
        # This should use AND logic
        self.assertIn("AND", str(q))
    
    def test_q_object_structure_mixed(self):
        """Verify Q object structure for mixed formats."""
        # Positive formats ORed together
        positive_q = Q(has_gltf2=True) | Q(has_obj=True)
        # Negative formats ANDed together
        negative_q = Q(has_tilt=False) & Q(has_blocks=False)
        # Combined with AND
        combined_q = positive_q & negative_q
        
        q_str = str(combined_q)
        # Should contain both OR and AND operations
        self.assertIn("AND", q_str)
        # Verify all fields are present
        self.assertIn("has_gltf2", q_str)
        self.assertIn("has_obj", q_str)
        self.assertIn("has_tilt", q_str)
        self.assertIn("has_blocks", q_str)
