# Import the required modules
from __future__ import annotations

import cv2 as cv
import matplotlib.pyplot as plt
import numpy as np
import os
import json
import pandas as pd
import openpyxl
import os
import shutil

from functions import create_directories, calculate_psnr, number_of_elements, total_number_of_elements, zigzag_scan, zigzag_unscan

# Define the quantization matrix
quantization_matrix = np.array(
    [
        [16, 11, 10, 16, 24, 40, 51, 61],
        [12, 12, 14, 19, 26, 58, 60, 55],
        [14, 13, 16, 24, 40, 57, 69, 56],
        [14, 17, 22, 29, 51, 87, 80, 62],
        [18, 22, 37, 56, 68, 109, 103, 77],
        [24, 35, 55, 64, 81, 104, 113, 92],
        [49, 64, 78, 87, 103, 121, 120, 101],
        [72, 92, 95, 98, 112, 100, 103, 99],
    ],
    dtype=np.float32,
)

loaded_quantalama = []
with open("veri.json", "r") as file:
    loaded_quantalama = json.load(file)

print(len(loaded_quantalama))

base_directory = "C:/Users/ilker/Desktop/deneme"
source_directory = os.path.join(base_directory, "pnomoni")

for index, filename in enumerate(os.listdir(source_directory)):
    if filename.startswith("image-"):
        folder_name = filename.split("-")[1].split(".")[0]

        plt_save_directory, compressed_image_directory, excel_file_directory = create_directories(base_directory, folder_name)

        img_path = os.path.join(source_directory, filename)

        print(f"Processed image {filename} in folder {folder_name}")

        for i in range(0, len(loaded_quantalama)):
            new_filename = f"compressed-{i}-{filename}"
            new_img_path = os.path.join(compressed_image_directory, new_filename)
            shutil.copy(img_path, new_img_path)

            quantization_matrix = np.array(loaded_quantalama[i], dtype=np.float32)
            print(quantization_matrix)

            def grayscale_jpeg_encoder(
                    img: np.ndarray[np.uint8], block_size: int, num_coefficients: int
            ) -> list[np.ndarray[np.int32]]:
                """
                Encodes a grayscale image using JPEG compression
                Returns a list of 1D arrays containing the first `num_coefficients`
                coefficients after performing zigzag scanning on each quantized block
                This is the JPEG encoded array
                """
                # Pad the image to make it divisible by the block size
                height, width = img.shape
                padded_height = height + (block_size - height % block_size) % block_size
                padded_width = width + (block_size - width % block_size) % block_size
                padded_img = np.zeros((padded_height, padded_width), dtype=np.uint8)
                padded_img[:height, :width] = img

                # Subtract 128 from the image
                padded_img = padded_img.astype(np.float32) - 128

                # Split the image into blocks of the given size
                blocks = [
                    padded_img[i: i + block_size, j: j + block_size]
                    for i in range(0, padded_height, block_size)
                    for j in range(0, padded_width, block_size)
                ]

                # Apply the Discrete Cosine Transform (DCT) to each block
                dct_blocks = [cv.dct(block) for block in blocks]

                # Resize the quantization matrix to match the block size
                resized_quantization_matrix = cv.resize(
                    quantization_matrix, (block_size, block_size), cv.INTER_CUBIC
                )

                # Quantize each DCT coefficient by dividing with the resized quantization matrix
                quantized_blocks = [
                    np.round(block / resized_quantization_matrix).astype(np.int32)
                    for block in dct_blocks
                ]

                # Perform zigzag scanning on each quantized block
                zigzag_scanned_blocks = [zigzag_scan(block) for block in quantized_blocks]

                # Retain only the first `num_coefficients` coefficients in each block
                first_num_coefficients = [
                    block[:num_coefficients] for block in zigzag_scanned_blocks
                ]

                return first_num_coefficients


            def grayscale_jpeg_decoder(
                    blocks: list[np.ndarray[np.int32]], img: np.ndarray[np.uint8], block_size: int
            ) -> np.ndarray[np.uint8]:
                """
                Decodes a grayscale image using JPEG compression from the JPEG encoded array
                Returns a 2D array containing the compressed image
                """
                # Calculated the padded height and width of the image
                height, width = img.shape
                padded_height = height + (block_size - height % block_size) % block_size
                padded_width = width + (block_size - width % block_size) % block_size

                # Resize the quantization matrix to match the block size
                resized_quantization_matrix = cv.resize(
                    quantization_matrix, (block_size, block_size), cv.INTER_CUBIC
                )

                # Unscan the zigzag scanned blocks to get the quantized blocks
                zigzag_unscanned_blocks = [zigzag_unscan(block, block_size) for block in blocks]

                # Dequantize the quantized blocks using the resized quantization matrix
                dequantized_blocks = [
                    block * resized_quantization_matrix for block in zigzag_unscanned_blocks
                ]

                # Apply the Inverse Discrete Cosine Transform (IDCT) to each dequantized block
                idct_blocks = [cv.idct(block) for block in dequantized_blocks]

                # Reconstruct the compressed image from the IDCT blocks
                compressed_img = np.zeros((padded_height, padded_width), dtype=np.float32)
                block_index = 0
                for i in range(0, padded_height, block_size):
                    for j in range(0, padded_width, block_size):
                        compressed_img[i: i + block_size, j: j + block_size] = idct_blocks[
                            block_index
                        ]
                        block_index += 1

                compressed_img += 128

                # Crop the image back to its original size
                compressed_img = np.clip(compressed_img, 0, 255)
                return compressed_img[:height, :width].astype(np.uint8)


            def color_jpeg_encoder(
                    img: np.ndarray[np.uint8], block_size: int, num_coefficients: int
            ) -> tuple[
                list[np.ndarray[np.int32]], list[np.ndarray[np.int32]], list[np.ndarray[np.int32]]
            ]:
                """
                Encodes a color image using JPEG compression
                Returns a tuple of 3 lists, each containing
                1D arrays containing the first `num_coefficients`
                coefficients after performing zigzag scanning on each quantized block
                This is the JPEG encoded array
                The three lists correspond to the blue, green, and red channels respectively
                """
                # Split the image into blue, green and red channels
                blue_channel, green_channel, red_channel = cv.split(img)

                # Encode each channel using grayscale_jpeg_encoder
                return (
                    grayscale_jpeg_encoder(blue_channel, block_size, num_coefficients),
                    grayscale_jpeg_encoder(green_channel, block_size, num_coefficients),
                    grayscale_jpeg_encoder(red_channel, block_size, num_coefficients),
                )


            def color_jpeg_decoder(
                    blocks: tuple[
                        list[np.ndarray[np.int32]],
                        list[np.ndarray[np.int32]],
                        list[np.ndarray[np.int32]],
                    ],
                    img: np.ndarray[np.uint8],
                    block_size: int,
            ) -> np.ndarray[np.uint8]:
                """
                Decodes a JPEG encoded color image
                Returns a 3D array containing the compressed image
                """
                # Split the grayscale image into its color channels
                blue_channel, green_channel, red_channel = cv.split(img)

                # Decode each color channel using grayscale_jpeg_decoder
                blue_channel = grayscale_jpeg_decoder(blocks[0], blue_channel, block_size)
                green_channel = grayscale_jpeg_decoder(blocks[1], green_channel, block_size)
                red_channel = grayscale_jpeg_decoder(blocks[2], red_channel, block_size)

                # Merge the decoded color channels into a color image
                return cv.merge((blue_channel, green_channel, red_channel))


            def jpeg_encoder(
                    img_path: str,
                    block_size: int,
                    num_coefficients: int,
                    color: bool,
            ) -> (
                    list[np.ndarray[np.int32]]
                    | tuple[
                        list[np.ndarray[np.int32]],
                        list[np.ndarray[np.int32]],
                        list[np.ndarray[np.int32]],
                    ]
            ):
                """
                Encodes an image using JPEG compression
                Returns the JPEG encoded array
                """
                if color:
                    # Load color image and apply color JPEG encoder
                    img = cv.imread(img_path, cv.IMREAD_COLOR)
                    return color_jpeg_encoder(img, block_size, num_coefficients)
                else:
                    # Load grayscale image and apply grayscale JPEG encoder
                    img = cv.imread(img_path, cv.IMREAD_GRAYSCALE)
                    return grayscale_jpeg_encoder(img, block_size, num_coefficients)


            def jpeg_decoder(
                    blocks: list[np.ndarray[np.int32]]
                            | tuple[
                                list[np.ndarray[np.int32]],
                                list[np.ndarray[np.int32]],
                                list[np.ndarray[np.int32]],
                            ],
                    img_path: str,
                    block_size: int,
                    color: bool,
            ) -> np.ndarray[np.uint8]:
                """
                Decodes an image using JPEG compression from its JPEG encoded array
                Returns a 2D or 3D array containing the compressed image
                """
                if color:
                    img = cv.imread(img_path, cv.IMREAD_COLOR)
                    return color_jpeg_decoder(blocks, img, block_size)
                else:
                    img = cv.imread(img_path, cv.IMREAD_GRAYSCALE)
                    return grayscale_jpeg_decoder(blocks, img, block_size)


            def analyze_image(
                    img_path: str, block_size: int, num_coefficients: int, color: bool
            ) -> tuple[
                np.ndarray[np.uint8],
                np.ndarray[np.uint8],
                float,
                float,
                list[np.ndarray[np.int32]]
                | tuple[
                    list[np.ndarray[np.int32]],
                    list[np.ndarray[np.int32]],
                    list[np.ndarray[np.int32]],
                ],
                bool,
            ]:
                """
                Analyzes the input image by performing JPEG compression,
                Returns the original and compressed images, and the PSNR and compression ratio
                This can be used to compare the quality of the compressed image
                """
                # Read the image
                img: np.ndarray[np.uint8] = None
                if color:
                    img = cv.imread(img_path, cv.IMREAD_COLOR)
                else:
                    img = cv.imread(img_path, cv.IMREAD_GRAYSCALE)

                # Encode the image using JPEG compression
                encoded_img = jpeg_encoder(img_path, block_size, num_coefficients, color)

                # Decode the image using JPEG compression
                compressed_img = jpeg_decoder(encoded_img, img_path, block_size, color)

                # Calculate the PSNR between the original and compressed images
                psnr = cv.PSNR(img, compressed_img)

                # Calculate the compression ratio
                n2 = total_number_of_elements(encoded_img, color)
                if n2 == 0:
                    # In this case, the compression ratio is very high
                    # But, we set it to 0 to avoid division by 0 so that our analysis becomes easier
                    compression_ratio = 0
                else:
                    compression_ratio = img.size / total_number_of_elements(encoded_img, color)

                compressed_img_path = new_img_path
                print(compressed_img_path)
                cv.imwrite(compressed_img_path, compressed_img)

                data = {
                    "PSNR": [psnr],
                    "Compression Ratio": [compression_ratio]
                }

                df = pd.DataFrame(data)

                # Excel dosyasına kaydetme
                excel_file_path = excel_file_directory +"-"+ str(i) + ".xlsx"
                df.to_excel(excel_file_path, index=False)
                print("Veriler Excel dosyasına kaydedildi:", excel_file_path)
                # Return the original image, compressed image, PSNR, and compression ratio
                # Also return the encoded image and whether the image is color or not
                # The encoded image is returned so that it can be written in a text file
                return_values = (img, compressed_img, psnr, compression_ratio, encoded_img, color)
                del img, compressed_img, encoded_img
                return return_values

            def plot_images(
                    img: np.ndarray[np.uint8],
                    compressed_img: np.ndarray[np.uint8],
                    psnr: float,
                    compression_ratio: float,
                    encoded_img: list[np.ndarray[np.int32]]
                                 | tuple[
                                     list[np.ndarray[np.int32]],
                                     list[np.ndarray[np.int32]],
                                     list[np.ndarray[np.int32]],
                                 ],
                    color: bool,
            ) -> None:
                fig, axs = plt.subplots(1, 2, figsize=(10, 5))
                fig.suptitle(
                    "PSNR = {:.2f}\nCompression Ratio = {:.2f}".format(psnr, compression_ratio)
                )

                with open("encoded_image.txt", "w") as f:
                    if color:
                        axs[0].imshow(cv.cvtColor(img, cv.COLOR_BGR2RGB))
                        axs[1].imshow(cv.cvtColor(compressed_img, cv.COLOR_BGR2RGB))
                        for row in zip(*encoded_img):
                            for element in row:
                                f.write(str(element) + " ")
                            f.write("\n")

                    else:
                        axs[0].imshow(img, cmap="gray")
                        axs[1].imshow(compressed_img, cmap="gray")
                        for row in encoded_img:
                            for element in row:
                                f.write(str(element) + " ")
                            f.write("\n")

                axs[0].set_title("Original Image")

                axs[1].set_title("Compressed Image")

                #plt.savefig(plt_save_directory + '.png')
                plt_filename = f"compressed-{folder_name}-{i}-plt.png"
                plt_save_path = os.path.join(plt_save_directory, plt_filename)
                plt.savefig(plt_save_path)
                print("Grafik kaydedildi:", plt_save_directory + '.png')
                # plt.show()
                del img, compressed_img, encoded_img


            def plot_graph(img_dir_path: str, color: bool, ):
                psnr_list = []
                compression_ratio_list = []
                for num_coefficients in [1, 3, 6, 10, 15, 28]:
                    psnr_values = []
                    compression_ratio_values = []
                    for img_file in os.listdir(img_dir_path):
                        img_path = os.path.join(img_dir_path, img_file)
                        _, _, psnr, compression_ratio, _, _ = analyze_image(
                            img_path, 8, num_coefficients, color
                        )
                        psnr_values.append(psnr)
                        compression_ratio_values.append(compression_ratio)
                    psnr_list.append(np.mean(psnr_values))
                    compression_ratio_list.append(np.mean(compression_ratio_values))

                plt.plot(compression_ratio_list, psnr_list, "o")
                plt.xlabel("Compression Ratio")
                plt.ylabel("PSNR")
                plt.title("PSNR vs Compression Ratio")

                plt.show()

                print("tablo-", i, ":", psnr)
                print("tablo-", i, ":", compression_ratio)


            # ======================================== Uncomment the following lines to test the code ========================================
            # ======================================== You can run both these functions one by one ========================================
            if __name__ == "__main__":
                """
                Replace the image path with the path to your image
                plot_images function plots the original and compressed images
                Also, it wries the encoded images to a text file encoded_image.txt
                """
                # plot_images(*analyze_image(img_path="path/to/your/image", block_size=8, num_coefficients=10, color=True))

                """
                Replaces the images folder with the path to your images folder
                plot_graph function plots the PSNR vs Compression Ratio graph
                for all the images in the images folder for different values of num_coefficients
                """
                # plot_graph(img_dir_path="path/to/your/image/folder", color=False)

                # img_path = "C:/Users/ilker/Desktop/pnomoni/image-2.jpg"
                block_size = 8
                num_coefficients = 10
                color = "y"
                plot_images(*analyze_image(img_path, block_size, num_coefficients, color))

