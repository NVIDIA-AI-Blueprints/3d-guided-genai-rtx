<h2>3D Guided Generative AI Blueprint</h2>

# Description: 
The 3D Guided Generative AI Blueprint unlocks greater control over image generation by laying out the content in Blender to guide the image layout. Users can quickly alter the look of the 3D scene using generative AI, and the image outputs can be iterated on by making simple changes in the 3D viewport - such as changing the image perspective by adjusting the camera angle in Blender. Creators can ideate on scene environments much faster using generative AI, and adjustments are made much faster due to the control offered by using the viewport as a depth map.    

The blueprint produces high-quality outputs by leveraging the FLUX1.dev-depth model. Black Forest Labs' state-of-the-art FLUX.dev models, and ComfyUI provides a flexible and convenient UI. The Flux1.dev-depth model is quantized to NVFP4 and accelerated on NVIDIA GPUs, doubling performance and enabling this workflow to run on consumer GPUs. Sample image generation times using 30 steps at 1024x1024 resolution on a GeForce RTX 5090:

| NVFP4| Native (FP8) |
| ------- | -------- |
| 11 sec  | 25  sec  |

This blueprint is for non-commercial use. Contact sales@blackforestlabs.ai for commercial terms.

We recommend a minimum of 32 GB of system RAM with 64GB+ recommended.

<details><summary><h1>STEP 1 - Blueprint Download/Installation</h1></summary>
# Installing the Blueprint:
Download the latest release of the Blueprint installer: https://github.com/SKilbride/3d-guided-genai-rtx/releases

Run the blueprint installer by double clicking on:  3DAI-Guided-BP-Installer.exe

Authorize the install when prompted:

<img width="340" height="303" alt="Screenshot 2026-01-15 115415" src="https://github.com/user-attachments/assets/7987b7ec-4fd4-480d-abf5-76b3ecac5177" />

(NOTE: The installer may take up to 3 minutes to initialize and display the GUI as the installation environment is built)

<img width="702" height="632" alt="image" src="https://github.com/user-attachments/assets/2a298895-0cab-47ff-ad9d-426b2979938a" />

Click the Install button
   
</details>

<details><summary><h1>STEP 2 - Verify ComfyUI Installation</h1></summary>


<details><summary><h2>Microsoft Windows</h2></summary>
   
Open the Windows "Run" dialog by pressing: ⊞ Win + R keys on your keyboard

<img width="399" height="206" alt="image" src="https://github.com/user-attachments/assets/09aee4be-24ca-4866-9557-b6c89be3934f" />

In the Run dialog enter the following command and hit the OK button.

```
%userprofile%\ComfyUI_BP\run_nvidia_gpu.bat
```

Expect a command terminal window to be displayed with output as the ComfyUI server starts

</details>

<details><summary><h2>Linux - TBD</h2></summary>
   
   TBD
   
</details>

Once ComfyUI has started the ComfyUI node graph interface should open in the default web browser, on first run the ComfyUI Template Broswer will generally be displayed

<img width="2560" height="1440" alt="image" src="https://github.com/user-attachments/assets/0559f076-9ff5-4896-9949-7945bdfc2bc5" />

Close the ComfyUI and assocaited command prompt terminal befpre proceeding

</details>

<details><summary><h1>STEP 3 - Configure Blender</h1></summary>

Once installation is complete start Blender and press open Preferences from the menu: Edit \>\>Preferences  
![Untitled-9](https://github.com/user-attachments/assets/c86d710d-39bf-48a4-8fc8-48b59ae16ebd)

Select the Add-On section , and click the checkbox next to ComfyUI BlenderAI node.  
Expand the ComfyUI BlenderAI node section by clicking on the \>  
![Untitled-10](https://github.com/user-attachments/assets/a8667460-d3ae-4e57-8bfe-10853dc2f7a1)

The Add-On will attempt to automatically configure the paths for the ComfyUI and Comfy Python locations. In the ComfyUI Path and the Python Path configuration section, verify that these paths match are correct. Alternatively, you can click the folder icon and navigate to the installation location and select the ComfyUI folder, and the python\_embedded folder in the ComfyUI installation. 

</details>

<details><summary><h1>STEP 4 - Correcting the Workflow</h1></summary>
It may be necessary to fix elements in the workflow which may have gotten unsyncronized.

<img width="708" height="104" alt="Menu_top" src="https://github.com/user-attachments/assets/3c1682f2-10fd-4f29-9372-6b355a984ec6" />

From the top menu tabs, select the "ComfyUI Detail" tab

Select the First Frame Node Tree from the drop down in the top middle of the viewport
<img width="551" height="179" alt="FirstFrame" src="https://github.com/user-attachments/assets/2bb99b26-28f5-42eb-9f58-04fbda69d8d2" />


You may notice that fields in some of the nodes are missing information, we need to correct this before the workflow can run properly

<img width="463" height="722" alt="Nodes" src="https://github.com/user-attachments/assets/1a8ba096-92b6-486e-b58f-c21245c19c47" />

In the UNET Model node se;ec the unet_name field and select flux1-depth-dev-nvfp4.safetensors
In the Dual Clip Loader select the clip1_name field and select t5xxl_fp8_e4m_scaled.safetensors from the dropdown.  (The clip2_name field should contain clip_l.safetensors)

See the example below for how the graph should look.

<img width="449" height="668" alt="nodes_fixed(3)" src="https://github.com/user-attachments/assets/e400b0ae-6d53-453b-9fa5-012b0083e08a" />




</details>
<details><summary><h1>STEP 5 - Running the Workflow</h1></summary>

From the Blender menu select File \>\> Open  
![Untitled-11](https://github.com/user-attachments/assets/0bec5bae-8cdb-4eff-a20e-569cf6a159f6)

Navigate to Documents \>\> Blender    
Select the **MotorCycle\_FF\_LF.blend** file  

<img width="1324" height="381" alt="OpenBlendFile" src="https://github.com/user-attachments/assets/aa878062-7fc5-4c57-a4ef-3d1351d748f4" />

Allow the executionof scripts (This script pauses the playback when reaching the end of an animation range instead of looping the animation)

<img width="665" height="293" alt="AllowScripts" src="https://github.com/user-attachments/assets/481b999e-c3e2-4b8c-b475-1ed92bcecb9a" />


<img width="2887" height="1630" alt="Viewport" src="https://github.com/user-attachments/assets/e0872b44-1ae2-4ad0-8c32-5658fd20252d" />

Click in the 3D viewport and hen press spacebar to play the animation which builds the scene.

<img width="1831" height="1196" alt="built_VP" src="https://github.com/user-attachments/assets/ef21bdea-53d0-47fd-aff1-ea86c1bc582f" />


If necessary expand the panel in the upper left viewport by clicking on the \< indicator. Alternatively move the mouse into the upper left viewport and press the “n” key on the keyboard.

<img width="955" height="778" alt="ComfyUI_BLENDER_GUI" src="https://github.com/user-attachments/assets/45ab1e4b-f4a8-4137-b94c-22fd15a27a99" />

Select the ComfyUI X Blender tab if needed. Click the **Launch/Connect to ComfyUI** button to start a local ComfyUI server instance. 

It may take up to two minutes to start the ComfyUI service and establish a connection.  
![Untitled-14](https://github.com/user-attachments/assets/fc0aed22-5f45-40ee-8d18-873a58424e1d)

NOTE:  The Blender system console can be opened from the Blender Menu selection Window \>\> Toggle System Console. The system console can help provide additional information about the ComfyUI startup process and provide updates while ComfyUI tasks are running.

Once ComfyUi has started and is ready the panel will change and a **Run** button will appear.  
<img width="570" height="847" alt="Prompt" src="https://github.com/user-attachments/assets/c7ccfdf0-4c10-494f-9899-f0469e4ade48" />


If the Run button does not appear or the **Launch/Connect to ComfyUI** reappears, check the system console for any error messages.

Click the Run button.

By default the sample workflow will use the viewport scene combined with the following prompt to generate an image that matches both the overall look of the 3D scene, and the text prompt:  
*“a professional photo from a Hollywood movie of a person wearing a black leather jacket on a red motorcycle racing through an alley in daytime rtraditional paper lanterns hang overhead and, the alley contains garbage cans, trash bags and wooden boxes,  doors and windows in the alley walls lead to quaint shops, the person is wearing a red  motorcycle helmet with a tinted visor and no logos, paper lanterns overhead, old bike against the wall”*

<img width="2971" height="1625" alt="Generated" src="https://github.com/user-attachments/assets/0d8091ef-24fb-458c-a991-5b4d4fa4a33c" />


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

Click on the fountain object and click delete on the keyboard to remove the motorcycle.  
<img width="2887" height="1630" alt="Viewport" src="https://github.com/user-attachments/assets/bcf41273-6861-41b3-a11b-a28071bfa19e" />


In the lower left area of the screen grab the person riding a bicycle object and drag it into the upper left viewport to the general location where the motorcycle was previously.   

Replace the entire prompt with one of these:  
*“a cellphone photo of a person riding a bicycle through an alley in daytime traditional paper lanterns hang overhead and, the alley contains garbage cans, trash bags and wooden boxes,  doors and windows in the alley walls lead to quaint shops, paper lanterns overhead, old bike against the wall”*

### Adjusting the Image Output Location
Change the output path in the SaveImage node to point to a location on your system where you would like to save generated images.
![Untitled-21](https://github.com/user-attachments/assets/f4189a22-e309-465a-a91c-eb259bc73434)



# Restarting the ComfyUI Server

If errors occur when working with the workflow it may be necessary to restart the ComfyUI Server. To restart ComfyUI, place your mouse cursor in the ComfyUI node graph area and press “N” to display the panel.  
![Untitled-22](https://github.com/user-attachments/assets/fdda5ed7-183f-4f2f-9268-bc5d78918682)

Click the ![image125](https://github.com/user-attachments/assets/065a8cc9-460e-48a0-abab-8a8dec9a0994) icon to stop ComfyUI.  
Click the ![image126](https://github.com/user-attachments/assets/fddc145f-ac73-4228-9639-e69be7abc8bd) icon again to restart ComfyUI, or click the **Launch/Connect to ComfyUI** button.

Re-run the workflow.
</details>


