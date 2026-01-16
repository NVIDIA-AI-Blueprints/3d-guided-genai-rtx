<h2>3D Guided Generative AI Blueprint</h2>

# Description: 
The 3D Guided Generative AI Blueprint unlocks greater control over image generation by laying out the content in Blender to guide the image layout. Users can quickly alter the look of the 3D scene using generative AI, and the image outputs can be iterated on by making simple changes in the 3D viewport - such as changing the image perspective by adjusting the camera angle in Blender. Creators can ideate on scene environments much faster using generative AI, and adjustments are made much faster due to the control offered by using the viewport as a depth map.    

The blueprint produces high-quality outputs by leveraging the FLUX.dev NIM, using Black Forest Labs' state-of-the-art FLUX.dev models, and ComfyUI provides a flexible and convenient UI. The models are quantized and accelerated on NVIDIA GPUs, doubling performance and enabling this workflow to run on consumer GPUs. Sample image generation times using 30 steps at 1024x1024 resolution on a GeForce RTX 5090:

| NIM | Native (FP8) |
| ------- | -------- |
| 11 sec  | 25  sec  |

This blueprint is ready for non-commercial use. Contact sales@blackforestlabs.ai for commercial terms.

> This blueprint supports the following NVIDIA GPUs:  RTX 5090, RTX 5090 Laptop, RTX 5080, RTX 4090, RTX 4090 Laptop, RTX 4080, RTX 6000 Ada. We recommend at least 48 GB of system RAM. 

<details>
<summary><h1>STEP 1 - NIM Pre-Requisite Installer</h1></summary>  
The NIM Prerequisite Installer requires Microsoft User Account Control (UAC) to be enabled.  UAC is enabled by default for Windows, but if it has been disabled, it must be enabled to ensure successful installation of the NIM Prerequisite Installer.  

  
More information on Microsoft UAC can found:  <a href="https://support.microsoft.com/en-us/windows/user-account-control-settings-d5b2046b-dcb8-54eb-f732-059f321afe18">HERE</a>


Download the [NIM Prerequisite Installer](https://assets.ngc.nvidia.com/products/api-catalog/rtx/NIMSetup.exe), and run the NIMSetup.exe file, and follow the instructions in the setup dialogs. This will install the necessary system components to work with NVIDIA NIMs on your system.
<img width="888" height="662" alt="image" src="https://github.com/user-attachments/assets/59f8e314-76ce-40d4-ae8c-3b096123e5b5" />

You will need to reboot your computer to complete the installation.
</details> 
<details>
  <summary><h1>STEP 2 - GIT Install</h1></summary>
Git is required and should be installed using winget from a command prompt:

```
winget install --id Git.Git
```
</details> 

<details><summary><h1>STEP 3 - Model License Acceptance</h1></summary>
<blockqoute>
<details>
   
<summary><h2>STEP 3a - Get or Verify HuggingFace API Access</h2></summary>
<blockquote>
<b>Obtain a Hugging Face API Access Token</b>  
Open and command prompt and type the following:  

```
set HF_TOKEN
```

If a value is shown for the HF\_TOKEN like in the image below you can skip the steps for obtaining a Hugging Face API Access Token and proceed to [Installing the Blueprint](#installing-the-blueprint)  
![Untitled-6](https://github.com/user-attachments/assets/c27ad5d1-e13b-4a0d-8a70-68d8c5a5ff33)

If the command returns that the environment variable HF\_TOKEN is not defined, complete the steps below.  
![Untitled-7](https://github.com/user-attachments/assets/cbac0a5b-5275-4a62-b921-7b47c48c0347)

Create a user account at [https://huggingface.co/](https://huggingface.co/) or login to your existing account.   
Select the “Settings” option on the left-hand menu.  
![Untitled-1](https://github.com/user-attachments/assets/2d01f9a7-94c4-4b25-85e7-f2acb2face04)

From the Left-Hand Menu select Access Tokens  
![Untitled-2](https://github.com/user-attachments/assets/e175526f-b1e0-4b94-add9-21ef2ec872d6)

Create a new Access Token with READ permissions. (Note: If you have an existing Access Token with read permissions you may use it instead of creating a new access token)

Copy your access token.
![Untitled-3](https://github.com/user-attachments/assets/b483af4d-7d4b-4887-902e-556fe169c88d)

### Create a HF_TOKEN environment variable 

Open a command prompt and issue the following command:


| setx HF_TOKEN *hf_access_token* |
| ----------- |

*hf_access_token* represents the actual access token value you created in the step above.
</blockquote>
</details>

<details>

<summary><h2>STEP 3b - Accept FLUX Non-Commercial License Agreements</h2></summary>

Once you have generated an access token you’ll need to agree to the FluxDev Non-Commercial License Agreement and acknowledge the Acceptable Use Policy by visiting:  [https://huggingface.co/black-forest-labs/FLUX.1-dev](https://huggingface.co/black-forest-labs/FLUX.1-dev)  
![Untitled-4](https://github.com/user-attachments/assets/b903d754-5b8b-43d2-a784-e0a7b075b1d1)

Click the Agree and access repository button.

Repeat the above process to accept the license for the following FLUX model variants:
| Model      |URL |
| ----------- | ----------- |
| FLUX.1-Canny-dev      | [https://huggingface.co/black-forest-labs/FLUX.1-Canny-dev](https://huggingface.co/black-forest-labs/FLUX.1-Canny-dev) |
| FLUX.1-Depth-dev      | [https://huggingface.co/black-forest-labs/FLUX.1-Depth-dev](https://huggingface.co/black-forest-labs/FLUX.1-Depth-dev) |
| FLUX.1-dev-onnx       | [https://huggingface.co/black-forest-labs/FLUX.1-dev-onnx](https://huggingface.co/black-forest-labs/FLUX.1-dev-onnx) |
| FLUX.1-Canny-dev-onnx | [https://huggingface.co/black-forest-labs/FLUX.1-Canny-dev-onnx](https://huggingface.co/black-forest-labs/FLUX.1-Canny-dev-onnx) |
| FLUX.1-Depth-dev-onnx | [https://huggingface.co/black-forest-labs/FLUX.1-Depth-dev-onnx](https://huggingface.co/black-forest-labs/FLUX.1-Depth-dev-onnx) |

</details>
</blockquote>
</details>
<details><summary><h1>STEP 4 - Blueprint Download/Installation</h1></summary>
# Installing the Blueprint:
Open a new Command Prompt and cd to the location where you would like the blueprint files to be installed.


Download the Blueprint and start the installation using the following command:
```
git clone https://github.com/NVIDIA-AI-Blueprints/3d-guided-genai-rtx.git && cd 3d-guided-genai-rtx && setup.bat
```
The Setup script will install several 3rd party software packages, by installing this blueprint you agree to the individual licenses for these software packages:
* Microsoft Visual C++ 2015-2022 Redistributable Package
* Blender
* Microsoft VisualStudio 2022 BuildTools
  
During the setup process you will be instructed to agree to the 3rd party licenses to continue. Press "y" and enter to accept the licenses and continue the installation.

Select <code>Yes</code> when presented with the User Account Control dialog.

The setup installer will install ComfyUI, the ComfyUI plugin for Blender, and other components required for the blueprint. 

As part of the setup process the NIM models will be downloaded and cached on the system for later use in the blueprint.

Installation may take up to 90 minutes depending on download speed.  
Once complete the installation will list the ComfyUI Path, and Python Path, this information can be used to verify the settings in the Blender ComfyUI add-on.   
![Untitled-5](https://github.com/user-attachments/assets/ef8f876b-883a-4afe-8820-5b97908da86c)
</details>

<details><summary><h1>STEP 5 - Configure Blender</h1></summary>

Once installation is complete start Blender and press open Preferences from the menu: Edit \>\>Preferences  
![Untitled-9](https://github.com/user-attachments/assets/c86d710d-39bf-48a4-8fc8-48b59ae16ebd)

Select the Add-On section , and click the checkbox next to ComfyUI BlenderAI node.  
Expand the ComfyUI BlenderAI node section by clicking on the \>  
![Untitled-10](https://github.com/user-attachments/assets/a8667460-d3ae-4e57-8bfe-10853dc2f7a1)

The Add-On will attempt to automatically configure the paths for the ComfyUI and Comfy Python locations. In the ComfyUI Path and the Python Path configuration section, verify that these paths match the paths shown at the end of the blueprint installation process. Alternatively, you can click the folder icon and navigate to the installation location and select the ComfyUI folder, and the python\_embedded folder in the ComfyUI installation. 
</details>

<details><summary><h1>STEP 6 - Running the Workflow</h1></summary>

From the Blender menu select File \>\> Open  
![Untitled-11](https://github.com/user-attachments/assets/0bec5bae-8cdb-4eff-a20e-569cf6a159f6)

Navigate to Documents \>\> Blender    
Select the **Guided\_GenAI\_BP.blend** file  
![Untitled-23](https://github.com/user-attachments/assets/7ecab817-b5bd-48a1-a4d3-70acd4bdbd6a)

![Untitled-12](https://github.com/user-attachments/assets/c590611c-de8c-409f-962f-a497f48228a5)

If necessary expand the panel in the upper left viewport by clicking on the \< indicator. Alternatively move the mouse into the upper left viewport and press the “n” key on the keyboard.
![Untitled-13](https://github.com/user-attachments/assets/5416a9ce-876d-4db0-bdfb-aba3553b2c85)

Select the ComfyUI X Blender tab if needed. Click the **Launch/Connect to ComfyUI** button to start a local ComfyUI server instance. 

It may take up to two minutes to start the ComfyUI service and establish a connection.  
![Untitled-14](https://github.com/user-attachments/assets/fc0aed22-5f45-40ee-8d18-873a58424e1d)

NOTE:  The Blender system console can be opened from the Blender Menu selection Window \>\> Toggle System Console. The system console can help provide additional information about the ComfyUI startup process and provide updates while ComfyUI tasks are running.

Once ComfyUi has started and is ready the panel will change and a **Run** button will appear.  
![Untitled-15](https://github.com/user-attachments/assets/9863ece0-0a29-4e0e-9362-535767c89091)

If the Run button does not appear or the **Launch/Connect to ComfyUI** reappears, check the system console for any error messages.

Click the Run button.

The first time the FLUX NIM is utilized it will need to download models from NVIDIA NGC and setup the FLUX NIM container, this process can take up to 20 minutes or more depending on the connection speed.

There will be an initial connection delay when first connecting to the NIM during a session which may take between 2-5 minutes. 

By default the sample workflow will use the viewport scene combined with the following prompt to generate an image that matches both the overall look of the 3D scene, and the text prompt:  
*“a stunning professional photo of a quaint village in the mountains in winter, a snow covered  fountain is visible in the center of the town square”*

##  Generating New Output

You can change the output, by changing either the text prompt, the 3D viewport information or both. NOTE:  When generating output, some parameter must be changed before it’s possible to generate a new output, either the 3D scene information, prompt, or some parameter. If nothing has been changed the workflow will not process a new image. 

The ComfyUI Connector panel is linked to the Input Text Node, you can change the prompt information here.   
![Untitled-16](https://github.com/user-attachments/assets/6bc83aba-1177-470d-a27b-7b48ee8ebab6)

In the prompt input area, add some additional information to the end of the existing text to change the output, for example try any of the following:  
“At sunset”  
“At night”  
“In the rain”

### Changing the 3D Scene

With the mouse in the upper left viewport press SHIFT \+ \~ to enter navigation mode. You can fly though the scene using the WASD keys and using the mouse to point in a direction. The E and F keys raise and lower the camera. Navigate the scene to find different camera angles.

### Replace Objects

Click on the fountain object and click delete on the keyboard to remove the fountain.  
![Untitled-18](https://github.com/user-attachments/assets/8a9c5fb3-85e9-4abd-b74f-4a6dc8322eda)

In the lower left area of the screen grab the boat object and drag it into the upper left viewport to the general location where the fountain was previously.   

Replace the entire prompt with one of these:  
“A stunning profession photo of a modern luxury boat in the canals of Venice, classical buildings, at sunset”  
“An abandoned boat sitting between rows of warehouses”  
![Untitled-19](https://github.com/user-attachments/assets/44988249-0c79-48a9-9fa0-29b5b5dd9a5f)
![Untitled-20](https://github.com/user-attachments/assets/54b2dced-d809-4454-8238-69ab5599ba5d)

### Adjusting the Image Output Location
Change the output path in the SaveImage node to point to a location on your system where you would like to save generated images.
![Untitled-21](https://github.com/user-attachments/assets/f4189a22-e309-465a-a91c-eb259bc73434)

## Stopping the NIM
Closing Blender after the FLUX NIM has been loaded may leave the NIM running in the background which can unneccesarily consume GPU and System resources, best practice is to stop the NIM when it is no longer needed, or before exiting Blender.

**Steps to stop the NIM:**
1. In the node tree, locate the **LoadNIMNode** node
2. ![Untitled-24](https://github.com/user-attachments/assets/5bd7cddb-ed55-4cc3-8b02-2e26f90f58b9)
3. Switch the *operation* setting from **Start** to **Stop**
4. ![Untitled-25](https://github.com/user-attachments/assets/1ab49581-5399-463f-b027-7e8baff915ea)
5. Click **Run** to run the workflow
6. This will cause an error in the NIMFLUXNode as the NIM is no longer available to run the workflow.
7. ![Untitled-26](https://github.com/user-attachments/assets/2bd59522-4e8f-485a-bd4a-c3865900ed8e)

### Manually stopping a NIM
1. If a NIM isn't stopped via the Stop method of the **LoadNIMNode** it may be necessary to manually stop the NIM via the command console
2. Open a windows command console and type:
3. > wsl podman ps -a
4. ![Untitled-27](https://github.com/user-attachments/assets/170be810-178f-44ad-bda2-89949105ef3d)
5. This will show the current active NIM containers
6. Note the name of the container **FLUX_DEPTH**
7. Issue the following command:
8. > wsl podman stop FLUX_DEPTH
9. ![Untitled-28](https://github.com/user-attachments/assets/b98f38c7-8ec8-4d65-bd50-6a655f0a35d8)
10. You can re-run the wsl podman ps -a command to verify that the FLUX_NIM is no longer running.

# Restarting the ComfyUI Server

If errors occur when working with the NIM it may be necessary to restart the ComfyUI Server. To restart ComfyUI, place your mouse cursor in the ComfyUI node graph area and press “N” to display the panel.  
![Untitled-22](https://github.com/user-attachments/assets/fdda5ed7-183f-4f2f-9268-bc5d78918682)

Click the ![image125](https://github.com/user-attachments/assets/065a8cc9-460e-48a0-abab-8a8dec9a0994) icon to stop ComfyUI.  
Click the ![image126](https://github.com/user-attachments/assets/fddc145f-ac73-4228-9639-e69be7abc8bd) icon again to restart ComfyUI, or click the **Launch/Connect to ComfyUI** button.

Re-run the workflow.
</details>


