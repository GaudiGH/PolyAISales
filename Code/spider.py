from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import pyodbc
import os
import requests
import json
from datetime import datetime
import logging
from logging.handlers import RotatingFileHandler

# 全局数据库连接
g_conn = None

# 配置日志
def setup_logger():
    """配置日志系统，同时输出到控制台和文件"""
    # 创建日志器
    logger = logging.getLogger('estate_spider')
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()  # 清除已存在的处理器
    
    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(funcName)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    
    # 文件处理器（按大小轮转，保留5个备份）
    log_file = 'estate_spider.log'
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=20*1024*1024,  # 20MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

# 初始化日志器
logger = setup_logger()

def get_Register_of_Transactions(driver, result):
    logger.info("get_Register_of_Transactions: begin")   
    result['TransactionsDate'] = '1900-01-01'
    result['RegisterofTransactions'] = '1900-01-01'
    try:
        transcations_section = driver.find_element(
            By.XPATH,
            '//*[contains(text(), "Register of Transactions")]/ancestor::div[1]'
        )
        if "Not yet available" in transcations_section.text:
            logger.info(transcations_section.text)
        else:        
            TransactionsDate = driver.find_element(By.XPATH, '//div[text()="Date and Time of Update"]/following::div[1]').text.strip()
            result['TransactionsDate'] = TransactionsDate.strip()
            logger.info(f"TransactionsDate：{TransactionsDate}")        
            transactions = driver.find_element(By.XPATH, '//a[text()="Register of Transactions"]')
            url = transactions.get_attribute("href")
            result['RegisterofTransactions'] = url.strip()
            logger.info(f"RegisterofTransactions：{url}")
            
    except Exception as e:
        logger.error(f"get_Register_of_Transactions: {e}", exc_info=e)
    logger.info("get_Register_of_Transactions: end")        
    return result;          

def get_Sales_Arrangement(driver, result):
    logger.info("get_Sales_Arrangement: begin")
    result['SalesArrangement'] = []
    result['SalesArrangementLatestDate'] = "1900-01-01"
    try:
        all_blocks = driver.find_elements(By.XPATH, "//div[contains(@class,'content-table')]")
        target_block = None

        for blk in all_blocks:
            try:
                if "Sales Arrangement" in blk.text:
                    target_block = blk
                    break
            except:
                continue

        if not target_block:
            logger.info("无Sales Arrangement板块，跳过")
            logger.info("get_Sales_Arrangement: end")
            return result

        if "Not yet available" in target_block.text:
            logger.info("Sales Arrangement Not yet available")
            return result
        
        # 定位 Sales Arrangement 板块（中英文兼容）
        sales_section = driver.find_element(
            By.XPATH,
            '//*[contains(text(), "Sales Arrangement")]/ancestor::div[1]'
        )
        
        # 取板块内的唯一表格
        table = sales_section.find_element(By.TAG_NAME, "table")
        rows = table.find_elements(By.TAG_NAME, "tr")

        for row in rows:
            try:
                # 取出当前行的所有单元格
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) < 2:
                    continue  # 跳过表头/无效行

                # 第1列：日期（带超链接）
                date_text = cells[0].text.strip()
                a_tag = cells[0].find_element(By.TAG_NAME, "a")
                url = a_tag.get_attribute("href").strip()
                
                # 第2列：文件大小
                file_size = cells[1].text.strip()

                # 组装结果
                item = {
                    "date": date_text,
                    "url": url,
                    "file_size": file_size
                }
                result['SalesArrangement'].append(item)
                result['SalesArrangementLatestDate'] = date_text
                logger.debug(f" Sales Arrangement | {date_text} | {file_size} | {url}")

            except Exception as e:
                logger.error(f"行抓取失败：{e}", exc_info=e)
                continue

    except Exception as e:
        logger.error(f"Sales Arrangement：{e}", exc_info=e)
        
    logger.info(f"共抓取 {len(result['SalesArrangement'])} 条销售安排记录")
    logger.info("get_Sales_Arrangement: end")
    return result
    
def get_Price_lists(driver, result):
    logger.info("get_Price_lists: begin")    
    result['PriceListsDate'] = datetime(1900, 1, 1)
    try:
        result['PriceLists'] = []
        price_section = driver.find_element(
            By.XPATH,
            '//*[contains(text(), "Price List")]/ancestor::div[1]'
        )
        if "Not yet available" in price_section.text:
            logger.info(price_section.text)
        else:
            # 只在 Price List 板块内找 table
            table = price_section.find_element(By.TAG_NAME, "table")
     
            rows = table.find_elements(By.TAG_NAME, "tr")
            for row in rows:
                try:
                    cells = row.find_elements(By.TAG_NAME, "td")
                    if len(cells) < 3:
                        continue

                    # 第 1 列：序号 + 链接（兼容 div 包裹 a）
                    serial_no = cells[0].text.strip()
                    a_tag = cells[0].find_element(By.TAG_NAME, "a")
                    url = a_tag.get_attribute("href")

                    # 第 3 列：日期
                    date = cells[2].text.strip()

                    item = {
                        "serial_no": serial_no,
                        "url": url,
                        "date": date
                    }
                    result['PriceLists'].append(item)
                    logger.info(f" {serial_no} | {date} | {url}")
                    d = datetime.strptime(date, "%d %b %Y")
                    if d > result['PriceListsDate']:
                        result['PriceListsDate'] = d
                except Exception as e:
                    logger.warning(f"处理Price List行失败: {e}", exc_info=e)
                    continue

    except Exception as e:
        logger.error(f"get_Price_lists: {e}", exc_info=e)
    result['PriceListsDate'] = result['PriceListsDate'].strftime("%Y-%m-%d")    
    logger.info("get_Price_lists: end")        
    return result;          
        
    
def get_Sales_Brochure(driver, result):
    logger.info("get_Sales_Brochure: begin")    
    ExaminationDate = None
    FirstPrintingdate = None
    result['BrochureFirstPrintingdate'] = "1900-01-01"
    result['BrochureExaminationDate'] = "1900-01-01"
    result['Brochure'] = {}
    try:
        brochure_section = driver.find_element(By.XPATH, '//div[contains(@class, "content-table") and .//h1[text()="Sales Brochure"]]')
        if "Not yet available" in brochure_section.text:
            logger.info(brochure_section.text)
        else:   
            logger.info(f"Current URL {driver.current_url}")
            FirstPrintingdate = driver.find_element(By.XPATH, '//div[text()="Date of First Printing"]/following::div[1]').text.strip()
            result['BrochureFirstPrintingdate'] = FirstPrintingdate.strip()
            logger.info(f"BrochureFirstPrintingdate：{FirstPrintingdate}")
            try:
                ExaminationDate = driver.find_element(By.XPATH, '//div[text()="Date of Examination"]/following::div[1]').text.strip();
                result['BrochureExaminationDate'] = ExaminationDate.strip()
                logger.info(f"BrochureExaminationDate：{ExaminationDate}")
            except Exception as e:
                ExaminationDate = None;     
#                logger.warning(f"未找到ExaminationDate: {e}", exc_info=e)

            # 匹配所有包含 Sales Brochure 的链接
            brochure_links = driver.find_elements(
                By.XPATH,
                '//a[contains(@title, "Sales Brochure") or contains(text(), "Sales Brochure")]'
            )

            for link in brochure_links:
                name = link.text.strip()
                url = link.get_attribute("href")
                if name == 'here':
                    continue
                result['Brochure'][name] = url           
                logger.debug(f" 找到：{name} → {url}")
    except Exception as e:
        logger.error(f"get_Sales_Brochure: {e}", exc_info=e)
    logger.info("get_Sales_Brochure: end")        
    return result;    

def get_estate_basic_inf(driver,result):
    logger.info("get_estate_basic_inf: begin")    
    result['name'] = '';
    result['address'] = '';
    try:
        basic_section = driver.find_element(By.XPATH, '//div[contains(normalize-space(.), "Selected Development")]')
        tr = basic_section.find_element(By.XPATH, './/tr[.//div[@title-th="Name of Development"]]')

        name_full = tr.find_element(By.XPATH, './td[1]').text.strip()
        parts = name_full.split('\n')
        name = parts[0]
        cname =''
        if len(parts) > 1:
            cname = parts[1]

        result['name'] = name;
        result['cname'] = cname;
        logger.info(f"楼盘名称：{name_full},{name},{cname}")
        
        phase_no = tr.find_element(By.XPATH, './td[2]').text.strip()       
        logger.info(f"期数：{phase_no}")
        result['phase_no'] = phase_no
        
        address = tr.find_element(By.XPATH, './td[4]').text.strip() 
        logger.info(f"地址：{address}")
        result['address'] = address;
    except Exception as e:
        logger.error(f"get_estate_basic_inf: {e}", exc_info=e)
    logger.info("get_estate_basic_inf: end")    
    return result;    

def open_website(cursor):        
    # 初始化 Chrome 浏览器
    driver = webdriver.Chrome()
    driver.maximize_window()

    # 目标网址
    main_url = "https://www.srpe.gov.hk/opip/disclaimer?return=%2Fall_development"
    driver.get(main_url)
    time.sleep(5)
    
    # 设置等待时间
    wait = WebDriverWait(driver, 5)

    logger.info("日志：已打开目标页面")

    lang = driver.execute_script("return document.documentElement.lang")
    logger.info(f"当前页面语言：{lang}")
     
    # 点击同意条款
    all_inputs = driver.find_elements(By.TAG_NAME, "input")
    agree_radio = driver.find_elements(By.XPATH, '//*[@id="skiptarget"]/form/div/div/div[1]/div[2]/div/label/span[1]/input')
    logger.info(f"同意条款单选框元素：{agree_radio}")

    driver.execute_script("arguments[0].click();", agree_radio[0])
    time.sleep(1)
    logger.info("日志：已点击同意条款")

    # 点击 Continue 按钮
    continue_btn = wait.until(
        EC.element_to_be_clickable((By.XPATH, '//button[text()="Continue"]'))
    )
    driver.execute_script("arguments[0].click();", continue_btn)
    logger.info("日志：已点击 Continue，正在跳转...")
    time.sleep(2)
    # 等待页面完全加载完成
    wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
    logger.info("日志：新页面已完全加载完成！")

    # 额外输出页面信息（纯文字）
    logger.info(f"当前页面标题：{driver.title}")
    logger.info(f"当前页面 URL：{driver.current_url}")

    time.sleep(15)

    logger.info("===================")    
    rows = driver.find_elements(By.XPATH, "//table/tbody/tr") 
    
    todayDone = query_done(cursor)
    results = [] 
    for i in range(len(rows)):
        row = None;
        for ii in range(10):
            try:       
                t = driver.find_elements(By.XPATH, '//table/tbody/tr')
                row = t[i]
                break;
            except Exception as e:
                logger.error(f"get item list: {e}", exc_info=e)
                time.sleep(6)
                if ii==5:
                    input()
           
            
        tds = row.find_elements(By.XPATH, "./td")
        if len(tds) < 2:
            continue        
        name_full = tds[0].text.strip()
        name_text = name_full.split('\n')[0]
#        name_text = name_full.replace("\nDevelopment Website", "").strip()        
        phase_text = tds[1].text.strip()
                    

        is_hit = any(
            item["name"] == name_text and item["phase"] == phase_text
            for item in todayDone
        )

        if is_hit:
            logger.info(f"今日已抓取，跳过：{name_text} {phase_text}")           
            continue

        first_link = row.find_elements(By.XPATH, './/a')[0]
        first_link.click()            

        time.sleep(6)        
            
        result = {}        
        result['url'] = driver.current_url;
        result = get_estate_basic_inf(driver, result)           
        result = get_Register_of_Transactions(driver, result)
        result = get_Price_lists(driver, result)
        result = get_Sales_Brochure(driver, result)
        result = get_Sales_Arrangement(driver, result)
     
#        print (result)
        with open("result.txt", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
 
        results.append(result)
        t = checkUpdate(result, cursor)
        if t == 1:
            insertNew(result, cursor)
        elif t == 2:
            backup(result, cursor)
            insertNew(result, cursor)
        elif t == 3:
            updateCheckStatus(result, cursor)
        
        driver.back()
        time.sleep(6)
        
    with open("results.txt", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info("All jobs done!!!!!!!!!!!!!")

def checkUpdate(result, cursor):
    global g_conn
    sql = """ 
    SELECT
      CASE
        WHEN NOT EXISTS (SELECT 1 FROM ai_estate_spider WHERE name = ? and phase = ? and version=1) THEN 1
        WHEN EXISTS (
            SELECT 1 FROM ai_estate_spider
            WHERE name = ? and phase = ?  and version=1
            AND (
                ? > ISNULL(BrochureFirstPrintingdate, '1900-01-01')
                OR ? > ISNULL(BrochureExaminationDate, '1900-01-01')
                OR ? > ISNULL(TransactionsDate, '1900-01-01')
                OR ? > ISNULL(PriceListsDate, '1900-01-01')
                OR ? > ISNULL(salesArragenmetnDate, '1900-01-01')
            )
        ) THEN 2
        ELSE 3
      END AS status
    """
    params = (result['name'],result['phase_no'],result['name'],result['phase_no'],result['BrochureFirstPrintingdate'],result['BrochureExaminationDate'], result['TransactionsDate'], result['PriceListsDate'], result['SalesArrangementLatestDate'])    
    cursor.execute(sql, params)
    print_full_sql(sql, params)
    need_update = cursor.fetchone()[0]
    logger.info(f"need_update: {need_update}")
    return need_update;
    
def updateCheckStatus(result, cursor):
    global g_conn
    sql = """ 
    UPDATE ai_estate_spider
    SET updatetime = GETDATE()
    WHERE name = ? and phase = ? and version=1;
    """
    params = (result['name'],result['phase_no'])
    cursor.execute(sql, params)
#    print_full_sql(sql, params)
    logger.info(f"updateCheckStatus. name={result['name']}")
    g_conn.commit()
    return;

def backup(result, cursor):
    global g_conn
    sql = """ 
    UPDATE ai_estate_spider_files
    SET version = version + 1 
    WHERE houseid in (select id from ai_estate_spider WHERE name = ?)
    """    
    params = (result['name'],)  # 修复元组参数格式
    cursor.execute(sql, params)
    print_full_sql(sql, params)
    
    sql = """ 
    UPDATE ai_estate_spider
    SET version = version + 1 
    WHERE name = ?;
    """
    params = (result['name'],)  # 修复元组参数格式
    cursor.execute(sql, params)
    print_full_sql(sql, params) 
    g_conn.commit()
    return;

def insertNew(result, cursor):
    global g_conn
    sql = """
    INSERT INTO ai_estate_spider (name, phase, address, BrochureFirstPrintingdate,BrochureExaminationDate, TransactionsDate,salesArragenmetnDate, PriceListsDate,chinese_name,url)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?,?, ?);
    """

    params = (result['name'], result['phase_no'], result['address'], result['BrochureFirstPrintingdate'],result['BrochureExaminationDate'], result['TransactionsDate'], result['SalesArrangementLatestDate'],result['PriceListsDate'],result['cname'], result['url'])    
    cursor.execute(sql, params)
    print_full_sql(sql, params)
    g_conn.commit();
    cursor.execute("SELECT id FROM ai_estate_spider WHERE name = ? order by id desc", (result['name'],))
    new_id = cursor.fetchone()[0]    
    logger.info(f"新插入记录ID：{new_id}")

    if result['TransactionsDate'] != '1900-01-01':
        sql = """
        INSERT INTO ai_estate_spider_files (houseid, name, date, type,  url)
        VALUES (?, 'transcations', ?, 'transcations', ?)
        """
        params = (new_id, result['TransactionsDate'], result['RegisterofTransactions'])
        print_full_sql(sql, params)
        cursor.execute(sql, params)   
        
    if len(result['Brochure']) != 0:
        for k,v in result['Brochure'].items():
            sql = """
            INSERT INTO ai_estate_spider_files (houseid, name, type,date, url)
            VALUES (?, ?, 'brochure',?,?)
            """
            params = (new_id, k, result['TransactionsDate'], v)    
            print_full_sql(sql, params)
            cursor.execute(sql, params) 
    #### Sale Arrangement ###
    for item in result['SalesArrangement']:
        sql = """
        INSERT INTO ai_estate_spider_files (houseid, name, type,date, url)
        VALUES (?, ?, 'salesarrangement',?, ?)
        """
        params = (new_id, item['date'],item['date'], item['url'])    
        print_full_sql(sql, params)
        cursor.execute(sql, params) 
    for item in result['PriceLists']:
        sql = """
        INSERT INTO ai_estate_spider_files (houseid, name, type, date, url)
        VALUES (?, ?, 'price',?, ?)
        """
        params = (new_id, item['serial_no'], item['date'],item['url'])    
        print_full_sql(sql, params)
        cursor.execute(sql, params)         
    g_conn.commit()
    
def db_insert(cursor,sql):
    cursor.execute(sql)

def print_full_sql(sql, params):
    """打印完整的SQL语句（替换参数），用于调试"""
    try:
        sql_copy = sql
        for p in params:
            # 字符串加引号，数字不加
            if isinstance(p, str):
                p_escaped = p.replace("'", "''")  # 处理单引号
                sql_copy = sql_copy.replace('?', f"'{p_escaped}'", 1)
            else:
                sql_copy = sql_copy.replace('?', str(p), 1)
        logger.debug(f"执行SQL：{sql_copy}")
    except Exception as e:
        logger.error(f"格式化SQL失败: {e}", exc_info=e)
        logger.info(f"原始SQL: {sql}")
        logger.info(f"参数: {params}")
    
def init_db():
    """初始化数据库连接"""
    global g_conn
    try:
        g_conn = pyodbc.connect(
            "DRIVER={ODBC Driver 17 for SQL Server};"
            "SERVER=192.168.120.242;"
            "DATABASE=PolyHK;"
            "UID=sa;"
            "PWD=eTk4@PM_5FsPn2-N;"
            "TrustServerCertificate=yes;"
        )
        logger.info("数据库连接成功")
        # 创建游标
        cursor = g_conn.cursor()
        return cursor
    except Exception as e:
        logger.error(f"数据库连接失败: {e}", exc_info=e)
        raise

def download_file(link, save_dir="sales_brochures"):
    """下载文件并返回保存的文件名"""
    from urllib.parse import urlparse
    
    # 自动创建文件夹（不存在就建）
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
        logger.info(f"创建文件夹: {save_dir}")

    parsed_url = urlparse(link)
    path = parsed_url.path

    # 核心修复：从路径里提取 .pdf 文件名
    parts = path.split("/")
    file_name = None
    for part in reversed(parts):
        if part.endswith(".pdf"):
            file_name = part
            break

    # 如果没找到就用默认名
    if not file_name:
        logger.error("ERROR: Can not find filename !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        file_name = "brochure.pdf"

    save_path = os.path.join(save_dir, file_name)

    logger.info(f"正在下载：{file_name}")
    try:
        resp = requests.get(link, stream=True, timeout=120)
        resp.raise_for_status()  # 检查HTTP错误
        with open(save_path, "wb") as f:
            f.write(resp.content)
        logger.info(f"下载完成：{save_path}")
        return file_name
    except Exception as e:
        logger.error(f"下载文件失败: {e}", exc_info=e)
        return None

def query_done(cursor):
    try:
        # MSSQL 今日日期查询
        sql = """ 
        SELECT name, phase
        FROM ai_estate_spider
        WHERE version = 1 
          AND CONVERT(DATE, UpdateTime) = CONVERT(DATE, GETDATE())
        """
        
        cursor.execute(sql)
        
        # 获取结果
        result = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
        result_list = [dict(zip(columns, row)) for row in result]

        logging.info(f"查询成功，返回条数：{len(result_list)}")
        return result_list

    except Exception as e:
        # 改成 logging 输出
        logging.error(f"查询失败：{str(e)}", exc_info=True)
        return []
        
def query_download(cursor):
    try:
        # MSSQL 今日日期查询
        sql = """ 
        SELECT id,trim(type),trim(url)
        FROM ai_estate_spider_files
        WHERE download = 0 
        """
        
        cursor.execute(sql)
        print_full_sql(sql, [])
        # 获取结果
        result = cursor.fetchall()
        logging.info(f"查询成功，返回条数：{len(result)}")
        return result

    except Exception as e:
        # 改成 logging 输出
        logging.error(f"查询失败：{str(e)}", exc_info=True)
        return []        
        
def update_download(cursor,idx, name, path, status):
    global g_conn
    try:
        sql = """ 
        Update ai_estate_spider_files
        set filename = ?, path=?, download=?
        WHERE id = ? 
        """
        if status == 1:
            sql = """ 
            Update ai_estate_spider_files
            set filename = ?, path=?, download=?, download_time=getdate()
            WHERE id = ? 
            """
        params = (name, path, status, idx)    
        print_full_sql(sql, params)
        cursor.execute(sql, params)   
        g_conn.commit()  
        return

    except Exception as e:
        # 改成 logging 输出
        logging.error(f"查询失败：{str(e)}", exc_info=True)
        return              
        
def truncate():
    """清空数据表"""
    global g_conn
    try:
        sql = """ 
        TRUNCATE TABLE ai_estate_spider_files;
        TRUNCATE TABLE ai_estate_spider;    
        """
        cursor.execute(sql)
        g_conn.commit()
        logger.info("数据表已清空")
    except Exception as e:
        logger.error(f"清空数据表失败: {e}", exc_info=e)
        raise
        

def download(cursor,rootdir):
    tasks = query_download(cursor)
    
    from urllib.parse import urlparse
    for idx, ftype, url in tasks:
        try:        
            #print (idx, ftype, url)
            #input()
            if ftype == 'salesarrangement':
                save_dir = rootdir + "/sales_brochures"
            elif ftype == 'brochure':
                save_dir = rootdir + "/brochure"
            elif ftype == 'transcations':
                save_dir = rootdir + "/transcations"
            elif ftype == 'price':
                save_dir = rootdir + "/price"
            else:
                update_download(cursor, idx, '', '', 10)
                continue;
                
            # 自动创建文件夹（不存在就建）
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
                logger.info(f"创建文件夹: {save_dir}")

            parsed_url = urlparse(url)
            path = parsed_url.path

            # 核心修复：从路径里提取 .pdf 文件名
            parts = path.split("/")
            file_name = None
            for part in reversed(parts):
                if part.endswith(".pdf"):
                    file_name = part
                    break

            # 如果没找到就用默认名
            if not file_name:
                logger.error("ERROR: Can not find filename !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                update_download(cursor, idx, '', '', 11)
                continue

            save_path = os.path.join(save_dir, file_name)

            logger.info(f"正在下载：{file_name}")
            try:
                resp = requests.get(url, stream=True, timeout=120)
                resp.raise_for_status()  # 检查HTTP错误
                with open(save_path, "wb") as f:
                    f.write(resp.content)
                logger.info(f"下载完成：{save_path}")
                update_download(cursor, idx, file_name, save_path, 1)
            except Exception as e:
                logger.error(f"下载文件失败: {e}", exc_info=e)
                update_download(cursor, idx, '', '', 2 )
            
        except Exception as e:
            # 改成 logging 输出
            logging.error(f"查询失败：{str(e)}", exc_info=True)            
    
    
if __name__ == "__main__":
    try:
        # 初始化数据库连接
        cursor = init_db()
        # 清空数据表
        #truncate()
        download(cursor,'./download')
        # 启动爬虫
#        driver = open_website(cursor)
    except Exception as e:
        logger.critical(f"程序执行失败: {e}", exc_info=e)
    finally:
        # 确保数据库连接关闭
        if g_conn:
            g_conn.close()
            logger.info("数据库连接已关闭")