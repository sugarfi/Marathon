var open = 'code.sh';

async function create(img, id, password) {
    var res = await fetch('/api/new', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'img':img,
            'id':id,
            'password':password,
        })
    });
    var out = await res.json();
    return out['id'];
}

async function load(img, id, password) {
    var res = await fetch('/api/load', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'img':img,
            'id':id,
            'password':password,
        })
    });
    var out = await res.json();
    return out['id'];
}

async function stdin(id, password, data) {
    await await fetch('/api/stdin', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'id':id,
            'password':password,
            'data':data,
        })
    });
}

async function stdout(id, password) {
    var res = await fetch('/api/stdout', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'id':id,
            'password':password,
        })
    });
    var out = await res.json();
    return out['data'];
}

async function rm(id, password) {
    var res = await fetch('/api/rm', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'id':id,
            'password':password,
        })
    });
}

async function write(id, password, file, data) {
    var res = await fetch('/api/write', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'id':id,
            'password':password,
            'file':file,
            'data':data,
        })
    });
    var out = await res.json();
    return out['data'];
}

async function read(id, password, file) {
    var res = await fetch('/api/read', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'id':id,
            'password':password,
            'file':file,
        })
    });
    var out = await res.json();
    return out['data'];
}

async function readdir(id, password, path) {
    var res = await fetch('/api/readdir', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            'id':id,
            'password':password,
            'path':path,
        })
    });
    var out = await res.json();
    return out['data'];
}

async function list(id, password, editor) {
    var files = await readdir(id, password, '/root');
    var tree = document.getElementById('files');
    while (tree.firstChild) {
        tree.removeChild(tree.firstChild);
    }
    files.forEach(function (file) {
        var div = document.createElement('div');
        div.className = 'file';
        div.innerText = file;
        div.onclick = async function (e) {
            write(id, password, open, editor.getValue());
            open = e.target.innerText;
            document.getElementById('open').innerText = open;
            var text = await read(id, password, `/root/${open}`);
            editor.setValue(text, 1);
        }
        tree.appendChild(div);
    });
}

async function main() {
    var password = sessionStorage.getItem('marathonPassword');
    var id;

    console.log('Getting ID...');
    var stored = sessionStorage.getItem('marathonID');
    var start = sessionStorage.getItem('new')
    var image = sessionStorage.getItem('marathonImg')
    if (start == 'yes') {
        idReq = load(image, stored, password);
    } else {
        idReq = create(image, stored, password);
    }
    idReq.then(async function (data) {
        console.log(`Got ID: ${data}`);
        id = data;
        document.getElementById('run').disabled = false;
        document.getElementById('open').innerText = open;
        text = await read(id, password, `/root/${open}`);
        editor.setValue(text, 1);
        await list(id, password, editor);
    });

    var editor = ace.edit('editor');
    editor.setTheme('tomorrow_night_eighties');
    editor.getSession().setMode('ace/mode/sh');

    var term = new Terminal({
        convertEol: true,
        rendererType: 'dom'
    });
    term.open(document.getElementById('terminal'));
    term.write('> ');

    document.getElementById('run').disabled = true;
    document.getElementById('run').onclick = async function() {
        await write(id, password, open, editor.getValue());
        term.clear();
        term.write('bash code.sh\n')
        await stdin(id, password, 'bash code.sh\n');
        data = await stdout(id, password);
        term.write(data);
        term.write('> ');
        await list(id, password, editor);
    }

    document.getElementById('new').onclick = async function() {
        var name = prompt('Filename:');
        await write(id, password, name, '');
        open = name;
        document.getElementById('open').innerText = open;
        var text = await read(id, password, `/root/${open}`);
        editor.setValue(text, 1);
        await list(id, password, editor);
    }

    document.getElementById('save').onclick = async function() {
        await write(id, password, open, editor.getValue());
    }

    var cmd = '';
    term.on('key', async function (key, e) {
        if (e.keyCode == 13) {
            term.write('\n');
            await stdin(id, password, cmd + '\n');
            cmd = '';
            var data = await stdout(id, password);
            term.write(data);
            term.write('> ');
        } else if (e.keyCode == 8) {
            if (term._core.buffer.x > 2) {
                term.write('\b \b');
                cmd = cmd.slice(0, -1);
            }
        } else {
            cmd += key;
            term.write(key);
        }
    });

    window.onbeforeunload = async function() {
        await rm(id, password);
    }
}

window.onload = main;
