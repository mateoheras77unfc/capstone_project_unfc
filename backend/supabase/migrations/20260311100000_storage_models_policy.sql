-- Migration: Storage policies for models bucket
-- Allows backend scripts to upload/download trained model files.

-- Allow all operations on the models bucket for authenticated and service role
INSERT INTO storage.buckets (id, name, public)
VALUES ('models', 'models', false)
ON CONFLICT (id) DO NOTHING;

CREATE POLICY "Allow full access to models bucket"
ON storage.objects
FOR ALL
TO authenticated, service_role
USING (bucket_id = 'models')
WITH CHECK (bucket_id = 'models');

-- Also allow anon role to upload (for scripts using anon key)
CREATE POLICY "Allow anon upload to models bucket"
ON storage.objects
FOR INSERT
TO anon
WITH CHECK (bucket_id = 'models');

CREATE POLICY "Allow anon read from models bucket"
ON storage.objects
FOR SELECT
TO anon
USING (bucket_id = 'models');

CREATE POLICY "Allow anon delete from models bucket"
ON storage.objects
FOR DELETE
TO anon
USING (bucket_id = 'models');
