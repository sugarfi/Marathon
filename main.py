import docker
import flask
import hashlib
import socket
import os
import uuid
import tarfile
import io

class Marathon(flask.Flask):
    def __init__(self):
        super().__init__('marathon')
        self.client = docker.from_env()
        self.running = {}
        self.sockets = {}
        self.funcs = {
            'new':self.new,
            'load':self.load,
            'rm':self.rm,
            'stdin':self.stdin,
            'stdout':self.stdout,
            'write':self.write,
            'read':self.read,
            'readdir':self.readdir,
        }
        self.names = {}
        self.imgs = {}
        self.add_url_rule('/', 'index', self.index)
        self.add_url_rule('/load', 'loadproject', self.loadproject, methods=['POST', 'GET'])
        self.add_url_rule('/new', 'newproject', self.newproject, methods=['POST', 'GET'])
        self.add_url_rule('/edit', 'edit', self.edit)
        self.add_url_rule('/api/<func>', 'api', self.api, methods=['POST', 'GET'])
    def index(self):
        return flask.render_template('index.html')
    def loadproject(self):
        if flask.request.method == 'POST':
            name = flask.request.form['name']
            password = hashlib.md5(bytes(flask.request.form['password'], 'utf-8')).digest()
            if name not in self.names:
                return {'ok':False, 'error':f'No such container {name}'}
            img = self.imgs[name]
            id = self.names[name]
            if self.running[id] != password:
                return {'ok':False, 'error':f'Invalid password for container {id}'}
            return flask.redirect(flask.url_for('edit', id=id, password=password, img=img, start='no'))
        return flask.render_template('loadproject.html')
    def newproject(self):
        if flask.request.method == 'POST':
            name = flask.request.form['name']
            img = flask.request.form['img']
            password = flask.request.form['password']
            if name in self.names:
                return {'ok':False, 'error':f'Container {name} already exists!'}
            id = str(uuid.uuid1())
            self.names[name] = id
            self.imgs[name] = img
            return flask.redirect(flask.url_for('edit', id=id, password=password, img=img, start='yes'))
        return flask.render_template('newproject.html')
    def edit(self):
        return flask.render_template('edit.html', **flask.request.args)
    def auth(self, id, password):
        if not self.running.get(id):
            return {'ok':False, 'error':f'No such container {id}'}
        if self.running[id] != password:
            return {'ok':False, 'error':f'Invalid password for container {id}'}
    def api(self, func):
        if flask.request.method != 'POST':
            return 'Please use the POST method to access this URL.'
        if func in self.funcs:
            return self.funcs[func](flask.request)
        return {'ok':False, 'error':f'No such API endpoint {func}'}, 400
    def new(self, req):
        img = req.json.get('img')
        password = hashlib.md5(bytes(req.json.get('password'), 'utf-8')).digest()
        id = req.json.get('id')
        path = os.path.join(os.getcwd(), f'files/{id}')
        if not os.path.exists(path):
            os.mkdir(path)
            open(f'{path}/code.sh', 'w').close()
        vol = {
            path: {'bind':'/root', 'mode':'rw'}
        }
        try:
            self.client.images.get(img)
        except:
            print('Pulling...')
            self.client.images.pull(img, 'latest')
            print('Done!')
        container = self.client.containers.run(img, tty=True, detach=True, working_dir='/root', volumes=vol, user=1000)
        try:
            container.rename(id)
        except docker.errors.APIError as e:
            return {'ok':False, 'error':f'Container {id} already exists'}, 400
        self.running[id] = password
        s = container.exec_run('bash', stdin=True, stderr=True, stdout=True, socket=True)[1]
        s._sock.setblocking(0)
        self.sockets[id] = s
        return {'ok':True, 'id':id}
    def load(self, req):
        img = req.json.get('img')
        password = hashlib.md5(bytes(req.json.get('password'), 'utf-8')).digest()
        id = req.json.get('id')
        path = os.path.join(os.getcwd(), f'files/{id}')
        if not os.path.exists(path):
            return {'ok':False, 'error':f'No stored volume named {id}'}, 400
        vol = {
            path: {'bind':'/root', 'mode':'rw'}
        }
        container = self.client.containers.run(img, tty=True, detach=True, working_dir='/root', volumes=vol, user=1000)
        try:
            container.rename(id)
        except docker.errors.APIError:
            container = self.client.containers.get(id)
        self.running[id] = password
        s = container.exec_run('bash', stdin=True, stderr=True, stdout=True, socket=True)[1]
        s._sock.setblocking(0)
        self.sockets[id] = s
        return {'ok':True, 'id':id}
    def rm(self, req):
        id = req.json.get('id')
        password = hashlib.md5(bytes(req.json.get('password'), 'utf-8')).digest()
        auth = self.auth(id, password)
        if auth:
            return auth
        container = self.client.containers.get(id)
        self.sockets[id].close()
        container.remove(force=True)
        return {'ok':True, 'id':id}, 200
    def stdin(self, req):
        id = req.json.get('id')
        password = hashlib.md5(bytes(req.json.get('password'), 'utf-8')).digest()
        data = req.json.get('data')
        auth = self.auth(id, password)
        if auth:
            return auth
        container = self.client.containers.get(id)
        s = self.sockets[id]
        s._sock.sendall(data.encode('utf-8'))
        return {'ok':True, 'id':id}, 200
    def stdout(self, req):
        id = req.json.get('id')
        password = hashlib.md5(bytes(req.json.get('password'), 'utf-8')).digest()
        auth = self.auth(id, password)
        if auth:
            return auth
        container = self.client.containers.get(id)
        s = self.sockets[id]
        going = True
        out = ''
        while going:
            try:
                byte = s._sock.recv(1)
            except socket.error:
                break
            if byte:
                chunk = s._sock.recv(16384)[7:]
                out += chunk.decode(errors='ignore')
            else:
                going = False
        return {'ok':True, 'id':id, 'data':out}, 200
    def write(self, req):
        id = req.json.get('id')
        password = hashlib.md5(bytes(req.json.get('password'), 'utf-8')).digest()
        file = req.json.get('file')
        data = req.json.get('data')
        auth = self.auth(id, password)
        if auth:
            return auth
        path = os.path.join(os.getcwd(), f'files/{id}')
        rel = os.path.relpath(path)
        if '..' in rel:
            return {'ok':False, 'error':'Nice try! No accessing paths outside of the volume directory!'}, 400
        if not os.path.exists(path):
            return {'ok':False, 'error':f'No stored volume named {id}'}, 400
        file = os.path.join(path, file)
        file = open(file, 'w')
        file.write(data)
        file.close()
        return {'ok':True, 'id':id}, 200
    def read(self, req):
        id = req.json.get('id')
        password = hashlib.md5(bytes(req.json.get('password'), 'utf-8')).digest()
        file = req.json.get('file')
        auth = self.auth(id, password)
        if auth:
            return auth
        container = self.client.containers.get(id)
        tar, stat = container.get_archive(file)
        chunks = b''
        for chunk in tar:
            chunks += chunk
        fileobj = io.BytesIO(chunks)
        tar = tarfile.open(fileobj=fileobj)
        file = tar.extractfile(os.path.basename(file))
        return {'ok':True, 'id':id, 'data':file.read()}, 200
    def readdir(self, req):
        id = req.json.get('id')
        password = hashlib.md5(bytes(req.json.get('password'), 'utf-8')).digest()
        path = req.json.get('path')
        auth = self.auth(id, password)
        if auth:
            return auth
        container = self.client.containers.get(id)
        tar, stat = container.get_archive(path)
        chunks = b''
        for chunk in tar:
            chunks += chunk
        fileobj = io.BytesIO(chunks)
        tar = tarfile.open(fileobj=fileobj)
        root = tar.getnames()[0]
        l = len(f'{root}/')
        files = [name[l:] for name in tar.getnames()[1:]]
        return {'ok':True, 'id':id, 'data':files}, 200
    def cleanup(self):
        for container in self.client.containers.list():
            try:
                container.remove(force=True)
            except:
                pass

app = Marathon()
app.secret_key = uuid.uuid4()
app.run(host='127.0.0.1', debug=True, port=5000)
app.cleanup()
