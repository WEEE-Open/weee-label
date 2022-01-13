-- Initialize the database.
-- Drop any existing data and create empty tables.

DROP TABLE IF EXISTS users;

CREATE TABLE users (
  id INTEGER PRIMARY KEY,  -- NO AUTOINCREMENT otherwise we can't compute the dataset to label section for each user
  username TEXT UNIQUE NOT NULL
);

INSERT INTO users (username) VALUES ('replace_me_with_secret_admin_username');
