FROM locustio/locust

USER root
RUN pip3 install --upgrade pip && pip3 install playwright locust locust-plugins
RUN playwright install
RUN playwright install-deps
#RUN apt-get install libatk1.0-0  libatk-bridge2.0-0  libcups2 libxkbcommon0  libatspi2.0-0  libxcomposite1 libxdamage1  libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2
RUN pip install python-dotenv 
#

