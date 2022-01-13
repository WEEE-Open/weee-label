# WEEE Label

A bad website for a good purpose
<hr />
A Flask backend + pure HTML frontend to allow people to easily help with binary dataset labeling

### How it works

User with ID=1 is admin and can add and remove users at `/manageusers`.  
All users can classify a data point by clicking on a button, until their share of data entries to label is completed.  
Their share is computed as the range of data points from 
```python
dataset_lower_limit = int(dataset_len * (user_id - 1) * user_to_label_ratio)
``` 
up to 
```python
dataset_upper_limit = int(dataset_len * user_id * user_to_label_ratio)
```
where
```python
user_to_label_ratio = 1 / users_count
```
meaning if there are 100 users, the dataset length is 1000, and my user ID is 20, I will have to label the `[190, 199]` entries data range.

### How to run

1. `python -m venv venv`
2. `source venv/bin/activate`
3. `pip install Flask`
4. `FLASK_APP=app.py FLASK_ENV=development flask run`
5. `FLASK_APP=app.py FLASK_ENV=development flask init-db` (first time only)
6. `FLASK_APP=app.py FLASK_ENV=development flask run` again (first time only)