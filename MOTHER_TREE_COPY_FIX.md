# Mother Tree Copy/Paste Fix

## Problem
When copying a mother tree with 28 cutting trees and pasting it:
- New mother tree only gets 5 cutting trees instead of 28
- Old mother tree retains 23 cutting trees instead of being cleared
- All cutting trees should move to the new mother tree

## Root Cause Analysis
The issue is in the cutting tree transfer logic during paste operations. The system needs to:
1. Ensure ALL cutting trees are included in the copy operation
2. Transfer ALL cutting trees to the new mother during paste
3. Remove ALL cutting trees from the old mother

## Solution

### 1. Enhanced Copy Operation
Ensure all cutting trees are included when copying a mother tree.

### 2. Complete Transfer Logic
When pasting a mother tree, transfer ALL its cutting trees and clear the old mother.

### 3. Verification System
Add logging to verify the complete transfer.

## Implementation

The fix involves modifying the cutting tree transfer logic to ensure complete transfer of all cutting trees from old mother to new mother.