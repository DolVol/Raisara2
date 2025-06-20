-- Fix User Table - Add Missing Columns
-- This script adds the missing columns to the user table that are causing login/registration errors

-- Check if columns exist and add them if they don't
-- PostgreSQL version

-- Add last_login column if it doesn't exist
DO $$ 
BEGIN 
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user' AND column_name = 'last_login'
    ) THEN
        ALTER TABLE "user" ADD COLUMN last_login TIMESTAMP;
        RAISE NOTICE 'Added last_login column';
    ELSE
        RAISE NOTICE 'last_login column already exists';
    END IF;
END $$;

-- Add previous_login column if it doesn't exist
DO $$ 
BEGIN 
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user' AND column_name = 'previous_login'
    ) THEN
        ALTER TABLE "user" ADD COLUMN previous_login TIMESTAMP;
        RAISE NOTICE 'Added previous_login column';
    ELSE
        RAISE NOTICE 'previous_login column already exists';
    END IF;
END $$;

-- Add login_count column if it doesn't exist
DO $$ 
BEGIN 
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'user' AND column_name = 'login_count'
    ) THEN
        ALTER TABLE "user" ADD COLUMN login_count INTEGER DEFAULT 0;
        RAISE NOTICE 'Added login_count column';
    ELSE
        RAISE NOTICE 'login_count column already exists';
    END IF;
END $$;

-- Verify the columns were added
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns 
WHERE table_name = 'user' 
AND column_name IN ('last_login', 'previous_login', 'login_count')
ORDER BY column_name;