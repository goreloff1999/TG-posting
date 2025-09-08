CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_raw_content_created_at ON raw_content(created_at);
CREATE INDEX IF NOT EXISTS idx_processed_content_created_at ON processed_content(created_at);
CREATE INDEX IF NOT EXISTS idx_published_posts_published_at ON published_posts(published_at);

-- Create function to update timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create triggers for automatic timestamp updates
CREATE TRIGGER update_processed_content_updated_at 
    BEFORE UPDATE ON processed_content 
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Insert initial data
INSERT INTO sources (name, platform, username, weight, is_active) VALUES
    ('Telegram Cointelegraph', 'telegram', '@Cointelegraph', 0.9, true),
    ('Telegram CoinDesk', 'telegram', '@CoinDesk', 0.9, true),
    ('Telegram TheBlock', 'telegram', '@TheBlock__', 0.8, true),
    ('Twitter CZ Binance', 'twitter', 'cz_binance', 0.9, true),
    ('Twitter Coin Bureau', 'twitter', 'coinbureau', 0.8, true)
ON CONFLICT (platform, username) DO NOTHING;
