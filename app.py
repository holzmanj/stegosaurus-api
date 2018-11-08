from flask import Flask, send_file, render_template, request, Blueprint
from flask_uploads import UploadSet, configure_uploads, IMAGES, ALL
from flask_restplus import Resource, Api
import requests
import hashlib
import werkzeug
import cv2
import os
import time
import traceback
import parsers
import time
from key_generator import generate_keys

import numpy as np
import tensorflow as tf
from neuralnet.src.config import Config
import nn_preproc as nn

app = Flask(__name__)
blueprint = Blueprint('api', __name__, url_prefix='/api')
api = Api(blueprint, title="SteGANographer API",
    description="Steganographic API for Stegosaurus using an early version of the neural network (no key support yet).")
app.register_blueprint(blueprint)

app.secret_key = os.urandom(16)

photoset = UploadSet('photos', IMAGES)
fileset  = UploadSet('files', ALL)
img_dir = 'static/img'
files_dir = 'static/files'

app.config['UPLOADED_PHOTOS_DEST'] = img_dir
app.config['UPLOADED_FILES_DEST'] = files_dir
configure_uploads(app, photoset)
configure_uploads(app, fileset)

# ╔╗╔╔═╗╦ ╦╦═╗╔═╗╦  ╔╗╔╔═╗╔╦╗  ╔═╗╔═╗╔╦╗╦ ╦╔═╗
# ║║║║╣ ║ ║╠╦╝╠═╣║  ║║║║╣  ║   ╚═╗║╣  ║ ║ ║╠═╝
# ╝╚╝╚═╝╚═╝╩╚═╩ ╩╩═╝╝╚╝╚═╝ ╩   ╚═╝╚═╝ ╩ ╚═╝╩  

cfg = Config()
# Prepare directories
root_dir = os.path.abspath("neuralnet")
model_dir = os.path.join(root_dir, "models")
model_dir = os.path.join(model_dir, cfg.MODEL_NAME)
if not os.path.exists(model_dir):
    print("Error: No model exists at %s" % model_dir)
    exit()

target_dir = os.path.join(root_dir, "production")
if not os.path.exists(target_dir):
    os.mkdir(target_dir)
in_dir = os.path.join(target_dir, "input")
out_dir = os.path.join(target_dir, "output")
if not os.path.exists(in_dir):
    os.mkdir(in_dir)
if not os.path.exists(out_dir):
    os.mkdir(out_dir)

# Load model
save_dir = os.path.join(model_dir, "data")
log_dir = os.path.join(model_dir, "logs")

# Use log file to infer current epoch
current_epoch = 0
log_file_name = os.path.join(log_dir, cfg.MODEL_NAME + "_log.csv")
if os.path.isfile(log_file_name):
    with open(log_file_name, 'r') as log_file:
        lines = log_file.readlines()
        if len(lines) > 1:
            current_epoch = int(lines[-1].split(',')[0])
            print("Current epoch: %d\n" % current_epoch)
        else:
            print("Error: Cannot infer epoch from log file...")
            exit()
else:
    print("Error: No log file from which to infer epoch")
    exit()

# Restore saved weights
weight_file_name = cfg.MODEL_NAME + '_train-' + str(current_epoch)
meta_file_name = weight_file_name + '.meta'

sess = tf.Session()
saver = tf.train.import_meta_graph(
    os.path.join(save_dir, meta_file_name))
saver.restore(sess, tf.train.latest_checkpoint(save_dir))

# ╔╗╔╔═╗╔╗╔   ╔═╗╔═╗╦  ╔═╗╔╗╔╔╦╗╔═╗╔═╗╦╔╗╔╔╦╗╔═╗
# ║║║║ ║║║║───╠═╣╠═╝║  ║╣ ║║║ ║║╠═╝║ ║║║║║ ║ ╚═╗
# ╝╚╝╚═╝╝╚╝   ╩ ╩╩  ╩  ╚═╝╝╚╝═╩╝╩  ╚═╝╩╝╚╝ ╩ ╚═╝

@app.route("/")
def home_page():
    return render_template("home.html")

@app.route("/img/<filename>")
def get_image(filename):
    filepath = os.path.join(img_dir, filename)
    if os.path.isfile(filepath):
        return send_file(filepath, mimetype="image/png")
    else:
        return "Image not found.", 404

@app.route("/api_log")
def api_log():
    with open("app.log", "r") as log:
        log_str = log.read()
        return render_template("log.html", log_text = log_str)

@app.route("/docs/keygen")
def docs_keygen():
    return render_template("keygen_doc.html")

@app.route("/docs/password_tester", methods=["GET", "POST"])
def password_tester():
    if request.method == "POST" and request.form["password"] is not None:
        key_dict = generate_keys(request.form["password"])
        return render_template("keygen_tester.html", password = request.form["password"],
                prelim = key_dict["prelim"], server_input = key_dict["server_input"],
                server_key = key_dict["server_key"], client_input = key_dict["client_input"],
                client_key = key_dict["client_key"])
    return render_template("keygen_tester.html")

# ╔═╗╔═╗╦  ╔═╗╦ ╦╔╗╔╔═╗╔╦╗╦╔═╗╔╗╔╔═╗
# ╠═╣╠═╝║  ╠╣ ║ ║║║║║   ║ ║║ ║║║║╚═╗
# ╩ ╩╩  ╩  ╚  ╚═╝╝╚╝╚═╝ ╩ ╩╚═╝╝╚╝╚═╝
# Everything documented in the Swagger page at /api

@api.route("/test")
@api.doc(id="test", description="Just for testing basic connection to API without dealing with form data or anything.")
class Test(Resource):
    def get(self):
        return "It worked!"
    
    @api.expect(parsers.test)
    def post(self):
        args = parsers.test.parse_args()
        msg = args["message"]
        return "The message you sent was: %s" % msg

@api.route("/get_capacity")
@api.doc(id="get_capacity", description="Get the amount of embeddable bytes in an image.")
class GetCapacity(Resource):
    @api.expect(parsers.get_capacity)
    def post(self):
        args = parsers.get_capacity.parse_args()
        try:
            file_name = os.path.join(img_dir, photoset.save(args["image"]))
        except Exception:
            app.logger.error("Client uploaded a file that was not an image.")
            return "File uploaded was not an image.", 422
        img = cv2.imread(file_name, cv2.IMREAD_COLOR)
        if img is None:
            app.logger.error("Image sent by client could not be read.")
            return "Unable to read file.", 422
        cap = nn.get_capacity(img)
        if args["formatted"] == True:
            msg = nn.format_capacity(cap)
        else:
            msg = str(cap)
        os.remove(file_name)
        return msg

@api.route("/insert")
@api.doc(id="insert", description="Insert content into vessel image using secret key.")
class Insert(Resource):
    @api.expect(parsers.insert)
    def post(self):
        args = parsers.insert.parse_args()
        time_0 = time.time()
        try:
            image_fname = os.path.join(img_dir, photoset.save(args["image"]))
        except:
            app.logger.error("Client sent a file for insertion that is not an image.")
            return "File uploaded for vessel image is not an image.", 422
        file_name = os.path.join(files_dir, fileset.save(args["content"]))
        output_fname = "%d.png" % int(time.time() * 1000)
        output_fpath = os.path.join(img_dir, output_fname)
        try:
            app.logger.info("Calling neural network insert for %s image." % nn.format_capacity(os.stat(image_fname).st_size))
            nn_time_0 = time.time()
            nn.insert(cfg, sess, image_fname, file_name, output_fpath)
            nn_time_diff = time.time() - nn_time_0
            app.logger.info("Neural network insert finished. Seconds elapsed: %s" % nn_time_diff)
            os.remove(image_fname)
            os.remove(file_name)
            time_diff = time.time() - time_0
            app.logger.info("Seconds elapsed handling insert request: %s" % time_diff)
            return request.url_root + "img/" + output_fname
        except Exception as e:
            os.remove(image_fname)
            os.remove(file_name)
            traceback.print_exc()
            app.logger.error(e)
            return str(e), 400

@api.route("/extract")
@api.doc(id="extract", description="Extract content from vessel image using secret key.")
class Extract(Resource):
    @api.expect(parsers.extract)
    def post(self):
        args = parsers.extract.parse_args()
        time_0 = time.time()
        # get image from url
        if args["image_url"] is not None and args["image_url"] != "":
            app.logger.info("Downloading image from url: %s" % args["image_url"])
            url_time_0 = time.time()
            r = requests.get(args["image_url"])
            url_time_diff = time.time() - url_time_0
            if r.status_code != 200:
                app.logger.error("Client sent a link that no data could be downloaded from.")
                return "Could not get data from link provided", 400
            ctype = r.headers["content-type"].split("/")
            if ctype[0] != "image":
                app.logger.error("Client sent a link to something that is not an image. Content-type: %s" % r.headers["content-type"])
                return "Data recieved from url was not an image. Content-type: %s" % r.headers["content-type"], 400
            image_fname = hashlib.md5(r.content).hexdigest() + "." + ctype[1]
            image_fname = os.path.join(img_dir, image_fname)

            app.logger.info("Seconds elapsed getting image from URL: %s" % url_time_diff)

            with open(image_fname, "wb") as f:
                f.write(r.content)

        # get image from request form data
        elif args["image"] is not None:
            try:
                image_fname = os.path.join(img_dir, photoset.save(args["image"]))
            except:
                app.logger.error("Client uploaded a file for extraction that was not an image.")
                return "File uploaded for vessel image is not an image.", 422
        else:
            app.logger.error("Client called extract without including either an image or image URL.")
            return "Must include either image, or image_url in request.", 400

        file_out = None
        try:
            app.logger.info("Calling neural network extract for %s image." % nn.format_capacity(os.stat(image_fname).st_size))
            nn_time_0 = time.time()
            file_out = nn.extract(cfg, sess, image_fname, files_dir)
            nn_time_diff = time.time() - nn_time_0
            app.logger.info("Neural network extract finished. Seconds elapsed: %s" % nn_time_diff)
            os.remove(image_fname)
            time_diff = time.time() - time_0
            app.logger.info("Seconds elapsed handling extract request: %s" % time_diff)
            return send_file(file_out, as_attachment=True, attachment_filename=os.path.basename(file_out))
        except Exception as e:
            if os.path.isfile(image_fname):
                os.remove(image_fname)
            if file_out is not None:
                if os.path.isfile(file_out):
                    os.remove(file_out)
            return str(e), 400
