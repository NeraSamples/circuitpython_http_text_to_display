# SPDX-FileCopyrightText: Copyright 2023 Neradoc, https://neradoc.me
# SPDX-License-Identifier: MIT
"""Show text from the web page on a display"""
import board
import json
import microcontroller
import time
import traceback
import os

import busio
from digitalio import *

from adafruit_httpserver.server import HTTPServer
from adafruit_httpserver.response import HTTPResponse
from adafruit_httpserver.mime_type import MIMEType
from adafruit_httpserver.status import CommonHTTPStatus

PORT = 8000
ROOT = "/www"

############################################################################
# Display
############################################################################

import displayio
SCALE = 1

if hasattr(board, "DISPLAY"):
    display = board.DISPLAY
else:
    # setup an external display in the display variable.
    raise OSError("Please setup an external display for this demo")

display.auto_refresh = False

############################################################################
# Interface on the display
############################################################################

import terminalio
from adafruit_display_text.label import Label
from adafruit_display_text import wrap_text_to_lines

FONT = terminalio.FONT

box = FONT.get_bounding_box()

color_bitmap = displayio.Bitmap(display.width, display.height, 1)
color_palette = displayio.Palette(1)
color_palette[0] = 0xFFFFFF  # White

splash = displayio.Group()

text_area = Label(
    FONT,
    scale=SCALE,
    text="Ready to receive.",
    color=0xFFFF00,
    anchored_position=(display.width // 2, 2),
    anchor_point=(0.5, 0),
)

splash.append(text_area)
display.show(splash)
display.refresh()

def wrap_the_text(text):
    LINE_WRAP = display.width // (box[0] * text_area.scale)
    return wrap_text_to_lines(text, LINE_WRAP)

############################################################################
# wifi
############################################################################

try:
    import wifi
    import socketpool

    if not wifi.radio.connected:
        wifi.radio.connect(
            os.getenv("WIFI_SSID"),
            os.getenv("WIFI_PASSWORD")
        )
    pool = socketpool.SocketPool(wifi.radio)
    server = HTTPServer(pool, root_path=ROOT)
    IP_ADDRESS = f"{wifi.radio.ipv4_address}"

except ImportError:
    from universal_socket import UniversalSocket
    from adafruit_esp32spi import adafruit_esp32spi
    import adafruit_esp32spi.adafruit_esp32spi_socket as socket

    esp32_cs = DigitalInOut(board.ESP_CS)
    esp32_ready = DigitalInOut(board.ESP_BUSY)
    esp32_reset = DigitalInOut(board.ESP_RESET)

    spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
    esp = adafruit_esp32spi.ESP_SPIcontrol(
        spi, esp32_cs, esp32_ready, esp32_reset
    )

    esp.connect_AP(
        os.getenv("WIFI_SSID"),
        os.getenv("WIFI_PASSWORD"),
    )

    socket.set_interface(esp)
    usock = UniversalSocket(socket, iface=esp)
    server = HTTPServer(usock, root_path=ROOT)
    IP_ADDRESS = "%d.%d.%d.%d" % tuple(esp.ip_address)

############################################################################
# server routes and app logic
############################################################################

# Application status data
class CurrentData:
    def __init__(self):
        self.text = "Ready to receive."
        self.size = 1
        self.color = 0xFFFF00
    def __repr__(self):
        return json.dumps({
            "text": self.text,
            "size": self.size,
            "color": f"#{self.color:06X}",
        })

current_data = CurrentData()

ERROR400 = CommonHTTPStatus.BAD_REQUEST_400

@server.route("/receive", method="POST")
def receive(request):
    try:
        # receive a text in the body
        body = json.loads(request.body)

        ########################################################
        # extract the size field
        size = body.get("size", None)
        # change the scale
        if size:
            print(f"{size=}")
            try:
                text_area.scale = size
                current_data.size = size
            except ValueError:
                print("Size invalid")

        ########################################################
        # extract the color field
        color = body.get("color", None).strip("#")
        if color:
            print(f"{color=}")
            try:
                text_area.color = int(color, 16)
                current_data.color = int(color, 16)
            except ValueError:
                print("Color invalid")

        ########################################################
        # extract the text field
        the_text = body.get("text", "")
        current_data.text = the_text
        # prepare the message for the screen
        message = "\n".join(wrap_the_text(the_text))
        # show the message
        text_area.text = message
        print("Received:", repr(message))

        ########################################################
        # refresh the display after all the changes
        display.refresh()
        # respond ok
        with HTTPResponse(request) as response:
            response.send("ok")

    except (ValueError, AttributeError) as err:
        # show the error if something went wrong
        traceback.print_exception(err)
        with HTTPResponse(request, status=ERROR400) as response:
            response.send("error")

@server.route("/status", method="GET")
def get_status(request):
    try:
        with HTTPResponse(request, content_type=MIMEType.TYPE_JSON) as response:
            out_data = repr(current_data)
            response.send(out_data)

    except (ValueError, AttributeError) as err:
        # show the error if something went wrong
        traceback.print_exception(err)
        with HTTPResponse(request, status=ERROR400) as response:
            response.send("error")

############################################################################
# start and loop
############################################################################

server.start(host=str(IP_ADDRESS), port=PORT)
print(f"Listening on http://{IP_ADDRESS}:{PORT}")

while True:
    server.poll()
    time.sleep(0.01)
