FROM tiangolo/uwsgi-nginx-flask:python3.8-alpine
WORKDIR /app
RUN rm ./*.py
COPY static static
COPY schema.sql .
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY templates templates
COPY *.py .
RUN mv app.py main.py
