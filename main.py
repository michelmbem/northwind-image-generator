import os, time, uuid, httpx, logging.handlers
import mssql_python as mssql
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image

# Load environment variables from .env file
load_dotenv()

# Configure logging
LOG_FILENAME = f"logs/app-{datetime.now().strftime('%Y%m%d')}.log"
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[
                        logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=10485760, backupCount=5),
                        logging.StreamHandler()
                    ])
log = logging.getLogger(__name__)

# Function definitions
def no_space(s):
    return s.strip().lower().replace(" ", "-")

def person_type(emp_id):
    match emp_id:
        case 1:
            return 'hispanic person'
        case 2:
            return 'person with a short beard and dark brown hair'
        case 3:
            return 'person with short black hair'
        case 4:
            return 'person with red hair'
        case 5:
            return 'black person'
        case 7:
            return 'bald person'
        case 8:
            return 'black person with fair skin and short dreadlocks'

    return 'person'

def generate_image(prompt, name, save_path):
    url = f"{os.getenv('AI_SERVICE_URL')}/prompt/{prompt}-{uuid.uuid4()}?width=500&height=550"

    while True:
        try:
            response = httpx.get(url)
            if response.status_code == 200:
                image_save_path = os.path.join(save_path, f"{no_space(name)}.jpg")
                os.makedirs(os.path.dirname(image_save_path), exist_ok=True)

                with open(image_save_path, 'wb') as f:
                    f.write(response.content)

                # Crop watermark/artifacts
                image = Image.open(image_save_path)
                image = image.crop((0, 0, image.width, image.height - 50))
                image.save(image_save_path)

                return image_save_path
            else:
                print(f"Retrying... Status code: {response.status_code}")
        except httpx.HTTPError as e:
            print(f"Request failed: {e}. Retrying...")

        time.sleep(5)  # Avoid rate-limiting

def read_all_bytes(file):
    with open(file, 'rb') as f:
        return f.read()

# Main program
if __name__ == '__main__':
    log.info('Ensuring output folder exists')
    save_path = 'employees-photos'
    os.makedirs(save_path, exist_ok=True)

    log.info('Connecting to database')
    # Using SQLPassword authentication
    conn_str = f"Server={os.getenv('DB_HOST')};Database={os.getenv('DB_NAME')};UID={os.getenv('DB_USERNAME')};PWD={os.getenv('DB_PASSWORD')};Encrypt=no;"
    connection = mssql.connect(conn_str)

    cursor = connection.cursor()

    log.info('Extracting data')
    cursor.execute("""
        SELECT
            EmployeeID,
            FirstName + ' ' + LastName,
            DateDiff(YEAR, BirthDate, GetDate()),
            Title
        FROM Employees
        WHERE EmployeeID <= 9
    """)
    employees = cursor.fetchall()

    for emp in employees:
        log.info(f"Generating a photo for {emp[0]} : {emp[1]}")
        ptype = person_type(emp[0])
        prompt = f"profile photo for a {ptype} named {emp[1]} aged {emp[2] - 30} working as {emp[3]}"
        image_path = generate_image(prompt, f"{emp[0]}-{emp[1]}", save_path)
        log.info(f"Generated: {image_path}")

        log.info('Saving the photo to the database')
        try:
            cursor.execute('UPDATE Employees SET Photo = ? WHERE EmployeeID = ?',
                           (read_all_bytes(image_path), emp[0]))
        except Exception as e:
            log.error(str(e))

    log.info('Closing connection')
    connection.commit()
    connection.close()

    log.info("Done!")
