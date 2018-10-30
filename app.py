from flask import Flask, send_file, render_template, request, Blueprint
from flask_uploads import UploadSet, configure_uploads, IMAGES, ALL
from flask_restplus import Resource, Api
import requests
import hashlib
import logging
import werkzeug
import lsb
import cv2
import os
import time
import traceback
import parsers
import time
from key_generator import generate_keys

app = Flask(__name__)
blueprint = Blueprint('api', __name__, url_prefix='/api')
api = Api(blueprint, title="LSB Dummy API",
    description="Steganographic API for Stegosaurus using LSB instead of neural network.")
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
        cap = lsb.get_capacity(img)
        if args["formatted"] == True:
            msg = lsb.format_capacity(cap)
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
        try:
            image_fname = os.path.join(img_dir, photoset.save(args["image"]))
        except:
            app.logger.error("Client sent a file for insertion that is not an image.")
            return "File uploaded for vessel image is not an image.", 422
        file_name = os.path.join(files_dir, fileset.save(args["content"]))
        output_fname = "%d.png" % int(time.time() * 1000)
        output_fpath = os.path.join(img_dir, output_fname)
        try:
            app.logger.info("Calling LSB insert for %s image." % lsb.format_capacity(os.stat(image_fname).st_size))
            time_0 = time.time()
            lsb.insert(image_fname, output_fpath, file_name)
            time_diff = time.time() - time_0
            app.logger.info("LSB insert finished. Seconds elapsed: %s" % time_diff)
            os.remove(image_fname)
            os.remove(file_name)
            return request.url_root + "img/" + output_fname
        except Exception as e:
            os.remove(image_fname)
            os.remove(file_name)
            app.logger.error(e)
            return str(e), 400

@api.route("/extract")
@api.doc(id="extract", description="Extract content from vessel image using secret key.")
class Extract(Resource):
    @api.expect(parsers.extract)
    def post(self):
        args = parsers.extract.parse_args()

        # get image from url
        if args["image_url"] is not None and args["image_url"] != "":
            r = requests.get(args["image_url"])
            if r.status_code != 200:
                app.logger.error("Client sent a link that no data could be downloaded from.")
                return "Could not get data from link provided", 400
            ctype = r.headers["content-type"].split("/")
            if ctype[0] != "image":
                app.logger.error("Client sent a link to something that is not an image.")
                return "Data recieved from url was not an image. Content-type: %s" % r.headers["content-type"], 400
            image_fname = hashlib.md5(r.content).hexdigest() + "." + ctype[1]
            image_fname = os.path.join(img_dir, image_fname)

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
            app.logger.info("Calling LSB extract for %s image." % lsb.format_capacity(os.stat(image_fname).st_size))
            time_0 = time.time()
            file_out = lsb.extract(image_fname, files_dir)
            time_diff = time.time() - time_0
            app.logger.info("LSB extract finished. Seconds elapsed: %s" % time_diff)
            os.remove(image_fname)
            return send_file(file_out, as_attachment=True, 
                attachment_filename=os.path.basename(file_out))
        except Exception as e:
            if os.path.isfile(image_fname):
                os.remove(image_fname)
            if file_out is not None:
                if os.path.isfile(file_out):
                    os.remove(file_out)
            return str(e), 400
