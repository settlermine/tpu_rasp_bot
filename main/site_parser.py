from bs4 import BeautifulSoup
import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import re
import os
import pickle


REGION = 'Asia/Tomsk'
GROUP = 36897
CLEANING_TIME = 12 * 3600

# Those methods only used inside file
def change_date_format_to_rasp(year: int, week: int) -> dict:
    week = int(week) + 18
    year = year - 1
    if week > 52:
        week = week - 52
        year = year + 1
    return {'year': year,
            'week': week}

def modification_date(filename):
    t = os.path.getmtime(filename)
    return datetime.datetime.fromtimestamp(t)

def get_page(group_id: int, year: int, week: int) -> str:
    options = webdriver.ChromeOptions()
    options.add_argument('headless')
    url = f"https://rasp.tpu.ru/gruppa_{group_id}/{year}/{week}/view.html"
    try:
        browser = webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                                   options=options)
        browser.get(url)
        html_code = browser.page_source
    except Exception as ex:
        print(ex)
    finally:
        browser.close()
        browser.quit()
    return html_code


def handle_cell(cell: BeautifulSoup) -> tuple:
    if 'free-day' in cell['class']:
        return None

    cell_content = cell.find_all(['div', 'hr'])
    lessons_in_cell = [{}]
    for cell_object in cell_content:
        if cell_object.name == 'hr':
            lessons_in_cell.append({})
            continue
        if cell_object.span:
            lessons_in_cell[-1]['subject'] = cell_object.text
            continue
        for a in cell_object.find_all('a'):
            if a['href']:
                if re.search('/user_', a['href']):
                    if 'teacher' not in lessons_in_cell[-1]:
                        lessons_in_cell[-1]['teacher'] = a.text
                    else:
                        lessons_in_cell[-1]['teacher'] += ', ' + a.text
                elif re.search('/sooruzhenie_', a['href']):
                    lessons_in_cell[-1]['building'] = a.text
                elif re.search('/pomeschenie_', a['href']):
                    lessons_in_cell[-1]['classroom'] = a.text

    for i in range(len(lessons_in_cell)):
        if 'subject' not in lessons_in_cell[i]:
            try:
                lessons_in_cell[i]['subject'] = lessons_in_cell[i-1]['subject']
            except KeyError:
                pass

    return tuple(lessons_in_cell)


def get_week_timetable(group_id: int, year: int, week: int) -> tuple:
    file_path = 'main/data/'+f'{week}_{year}_{group_id}.bin'
    if os.path.isfile(file_path):
        if (datetime.datetime.now() - modification_date(file_path)).total_seconds() < CLEANING_TIME:
            print('Inside if')
            with open(file_path, 'rb') as file:
                week_timetable = pickle.load(file)
                return week_timetable
        else:
            os.remove(file_path)      

    html_code = get_page(group_id, year, week)
    soup = BeautifulSoup(html_code, 'lxml')
    table_rows = soup.find('tbody', class_='text-center').find_all('tr')

    week_timetable = []
    free_days_indicies = []
    for table_row in table_rows:
        cells_in_row = table_row.find_all('td')[1:]
        lessons_list = []
        i = 0
        for cell in cells_in_row:
            while i in free_days_indicies:
                lessons_list.append(None)
                i += 1
            res = handle_cell(cell)
            lessons_list.append(res)
            if res is None:
                free_days_indicies.append(i)
            i += 1

        week_timetable.append(lessons_list)
    week_timetable = tuple(zip(*week_timetable))

    with open(file_path, 'wb') as file:
        pickle.dump(week_timetable, file)

    return week_timetable


#Method for usage
def get_day_timetable(group_id: int, date: datetime.date):
    format_date = change_date_format_to_rasp(date.year, date.isocalendar()[1])
    date_string = f'{str(date.day).zfill(2)}.{str(date.month).zfill(2)}.{str(date.year)[-2:]}'
    if date.weekday() < 6:
        week_timetable = get_week_timetable(group_id, **format_date)
        return {'date': date_string, 'weekday': date.weekday(), 'timetable': week_timetable[date.weekday()]}
    if date.weekday() == 6:
        return {'date': date_string, 'weekday': date.weekday(), 'timetable': (None, None, None, None, None, None, None)}

if __name__ == '__main__':
    get_day_timetable(36897, datetime.datetime.now())