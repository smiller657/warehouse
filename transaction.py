import psycopg2.extras
import psycopg2
from exceptions import *
from db import *

INVENTORYUPDATE = 'UPDATE inventory SET quantity = %s WHERE productid = %s AND warehouseid = %s;'
INVENTORYINSERT = 'INSERT INTO inventory (productid, warehouseid, quantity) VALUES (%s, %s, %s);'
QUANTITY = 'SELECT quantity FROM inventory WHERE productid = %s AND warehouseid = %s;'
PRODUCTINSERT = 'INSERT INTO products (name, description, price, pnumber) VALUES (%s, %s, %s, %s) RETURNING id;'
LASTID = 'SELECT id FROM {0} ORDER BY id DESC LIMIT 1;'

NOWAREHOUSE = 'No warehouse with id {0}: Line {1}'
NOPRODUCT = 'No product with id {0}: Line {1}'

def quantity(warehouseId, productId, cache, db):
	cursor = db.cursor()
	if (warehouseId, productId) in cache:
		return cache[(warehouseId, productId)]
	query = cursor.mogrify(QUANTITY, (productId, warehouseId))
	cursor.execute(query)
	temp = cursor.fetchone()
	return temp[0] if temp != None else 0

def newProduct(db, data):
	cursor = db.cursor()
	toId = data[0]
	prodName = data[1]
	prodDesc = data[2]
	quantity = data[3]
	price = data[4]
	prodNum = data[5]
	
	query = cursor.mogrify(PRODUCTINSERT, (prodName, prodDesc, price, prodNum))
	cursor.execute(query)
	prodId = cursor.fetchone()
	query = cursor.mogrify(INVENTORYINSERT, (prodId, toId, quantity))
	cursor.execute(query)

def restock(db, data):
	cursor = db.cursor()
	toId = data[0]
	product = data[1]
	quantity = data[2]
	query = cursor.mogrify(INVENTORYUPDATE, (product, toId, quantity))
	cursor.execute(query)

def transfer(db, data):
	cursor = db.cursor()
	fromId = data[0]
	toId = data[1]
	product = data[2]
	transferQuant = data[3]

	query = cursor.mogrify(QUANTITY, (product, fromId))
	cursor.execute(query)
	fromQuant = cursor.fetchone()[0]

	query = cursor.mogrify(QUANTITY, (product, toId))
	cursor.execute(query)
	toQuant = cursor.fetchone()

	query = cursor.mogrify(INVENTORYUPDATE, (fromQuant - transferQuant, product, fromId))
	cursor.execute(query)

	if toQuant:
		query = cursor.mogrify(INVENTORYUPDATE, (toQuant[0] + transferQuant, product, toId,))
	else:
		query = cursor.mogrify(INVENTORYINSERT, (product, toId, transferQuant))
	cursor.execute(query)


def validate(line, data, lastProduct, lastWarehouse, db, cache):
	cursor = db.cursor()
	if len(data) == 6:
		data[:] = [d.strip() for d in data]
		data[0] = int(data[0])
		data[3] = int(data[3])
		data[4] = float(data[4])
		if data[0] > lastWarehouse:
			raise InvalidID(NOWAREHOUSE.format(data[0], line))
		lastProduct += 1
		cache[(data[0], lastProduct)] = data[3]
		return lastProduct
	elif len(data) == 3:
		data[:] = [int(d.strip()) for d in data]
		if data[0] > lastWarehouse:
			raise InvalidID(NOWAREHOUSE.format(data[0], line))
		if data[1] > lastProduct:
			raise InvalidID(NOPRODUCT.format(data[1], line))
		toQuant = quantity(data[0], data[1], cache, db)
		cache[(data[0], data[1])] = toQuant + data[2]
	elif len(data) == 4:
		data[:] = [int(d.strip()) for d in data]
		if data[0] > lastWarehouse:
			raise InvalidID(NOWAREHOUSE.format(data[0], line))
		if data[1] > lastWarehouse:
			raise InvalidID(NOWAREHOUSE.format(data[1], line))
		if data[2] > lastProduct:
			raise InvalidID(NOPRODUCT.format(data[2], line))
		fromQuant = quantity(data[0], data[2], cache, db)
		if data[3] > fromQuant:
			raise InventoryOverdraft('Transfering more than warehouse has in stock: Line {0}'.format(line))
		toQuant = quantity(data[1], data[2], cache, db)
		cache[(data[0], data[2])] = fromQuant - data[3]
		cache[(data[1], data[2])] = toQuant + data[3]
	else:
		raise InvalidOperation('Invalid operation: Line {0}'.format(line))

def processFile(csvName):
	db = connect()
	cursor = db.cursor()

	query = cursor.mogrify(LASTID.format('warehouses'))
	cursor.execute(query)
	result = cursor.fetchone()
	lastWarehouse = result[0] if result != None else 0
	query = cursor.mogrify(LASTID.format('products'))
	cursor.execute(query)
	result = cursor.fetchone()
	lastProduct = result[0] if result != None else 0

	csv = open(csvName, 'r').readlines()
	csv = [(line + 1, csv[line].strip().split(',')) for line in range(len(csv)) if csv[line][0] not in ('#', '\n')]
	# data = {line: data[line].strip().split(',') for line in data if csv[line][0] not in ('#', '\n')]
	errors = []
	cache = {}
	for line, data in csv:
		try:
			lp = validate(line, data, lastProduct, lastWarehouse, db, cache)
			lastProduct = lp if lp != None else lastProduct
		except ValueError:
			errors.append('Improper data type at line {0}'.format(line))
		except Exception as e:
			errors.append(str(e))
	if errors:
		return errors

	newProds = [i[1] for i in csv if len(i[1]) == 6]
	restocks = [i[1] for i in csv if len(i[1]) == 3]
	transfers = [i[1] for i in csv if len(i[1]) == 4]

	for i in newProds:
		newProduct(db, i)
		db.commit()
	for i in restocks:
		restock(db, i)
		db.commit()
	for i in transfers:
		transfer(db, i)
		db.commit()
