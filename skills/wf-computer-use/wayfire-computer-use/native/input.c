#define _GNU_SOURCE
#include <wayland-client.h>
#include <xkbcommon/xkbcommon.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "pointer.h"
#include "keyboard.h"
static struct wl_display *display;
static struct wl_seat *seat;
static struct zwlr_virtual_pointer_manager_v1 *pm;
static struct zwp_virtual_keyboard_manager_v1 *km;
static struct zwlr_virtual_pointer_v1 *pointer;
static struct zwp_virtual_keyboard_v1 *keyboard;
static unsigned buttons[768], keys[768];
static uint32_t now(void);
static struct xkb_context *context;
static char *base_keymap;
static unsigned output_count, seat_count, pointer_version;
static struct output {struct wl_output *handle; char name[128];} outputs[32];
static void geometry(void*d,struct wl_output*o,int32_t x,int32_t y,int32_t w,int32_t h,int32_t sub,const char*make,const char*model,int32_t transform){(void)d;(void)o;(void)x;(void)y;(void)w;(void)h;(void)sub;(void)make;(void)model;(void)transform;}
static void mode(void*d,struct wl_output*o,uint32_t flags,int32_t w,int32_t h,int32_t refresh){(void)d;(void)o;(void)flags;(void)w;(void)h;(void)refresh;}
static void done(void*d,struct wl_output*o){(void)d;(void)o;}
static void scale(void*d,struct wl_output*o,int32_t factor){(void)d;(void)o;(void)factor;}
static void output_name(void*d,struct wl_output*o,const char*name){(void)o;snprintf(((struct output*)d)->name,128,"%s",name);}
static void description(void*d,struct wl_output*o,const char*name){(void)d;(void)o;(void)name;}
static const struct wl_output_listener output_listener={.geometry=geometry,.mode=mode,.done=done,.scale=scale,.name=output_name,.description=description};
static int upload(const char *text) {
 int fd=memfd_create("wf-keymap",MFD_CLOEXEC);size_t length=strlen(text)+1;
 if(fd<0)return -1;
 if(write(fd,text,length)!=(ssize_t)length){close(fd);return -1;}
 zwp_virtual_keyboard_v1_keymap(keyboard,1,fd,length);close(fd);
 return wl_display_roundtrip(display);
}
static int unicode_character(unsigned codepoint) {
 if(codepoint>0x10ffff || (codepoint>=0xd800 && codepoint<=0xdfff)) return -1;
 char source[512];
 snprintf(source,sizeof(source),"xkb_keymap { xkb_keycodes { include \"evdev+aliases(qwerty)\" }; xkb_types { include \"complete\" }; xkb_compatibility { include \"complete\" }; xkb_symbols { include \"pc+us\" key <AC01> { [ U%04X ] }; }; };",codepoint);
 struct xkb_keymap *map=xkb_keymap_new_from_string(context,source,XKB_KEYMAP_FORMAT_TEXT_V1,0);
 if(!map)return -1;
 char *text=xkb_keymap_get_as_string(map,XKB_KEYMAP_FORMAT_TEXT_V1);
 int result=upload(text);free(text);xkb_keymap_unref(map);
 if(result<0)return -1;
 usleep(50000); /* Experimental client keymap-settling probe. */
 zwp_virtual_keyboard_v1_key(keyboard,now(),30,1);
 zwp_virtual_keyboard_v1_key(keyboard,now(),30,0);
 if(wl_display_roundtrip(display)<0)return -1;
 usleep(50000);
 return upload(base_keymap);
}
static uint32_t now(void) {struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t);return (uint32_t)(t.tv_sec*1000+t.tv_nsec/1000000);}
static void global(void *data, struct wl_registry *r,uint32_t name,const char *iface,uint32_t version) {
 (void)data;
 if (!strcmp(iface,"wl_seat")) {seat_count++;if(!seat)seat=wl_registry_bind(r,name,&wl_seat_interface,1);}
 if (!strcmp(iface,"wl_output")) {
  if(output_count>=32)return;
  struct output *out=&outputs[output_count++];
  out->handle=wl_registry_bind(r,name,&wl_output_interface,version<4?version:4);
  wl_output_add_listener(out->handle,&output_listener,out);
 }
 if (!strcmp(iface,"zwlr_virtual_pointer_manager_v1")) {pointer_version=version<2?version:2;pm=wl_registry_bind(r,name,&zwlr_virtual_pointer_manager_v1_interface,pointer_version);}
 if (!strcmp(iface,"zwp_virtual_keyboard_manager_v1")) km=wl_registry_bind(r,name,&zwp_virtual_keyboard_manager_v1_interface,1);
}
static void removed(void *d,struct wl_registry *r,uint32_t n){(void)d;(void)r;(void)n;}
static const struct wl_registry_listener listener={global,removed};
static void release(void){
 for(unsigned i=0;i<768;i++){
  if(keys[i]) {zwp_virtual_keyboard_v1_key(keyboard,now(),i,0);keys[i]=0;}
  if(buttons[i]) {zwlr_virtual_pointer_v1_button(pointer,now(),i,0);buttons[i]=0;}
 }
 zwp_virtual_keyboard_v1_modifiers(keyboard,0,0,0,0);
 zwlr_virtual_pointer_v1_frame(pointer);
 wl_display_roundtrip(display);
}
int main(int argc,char **argv){
 display=wl_display_connect(NULL);if(!display){fputs("WAYLAND_UNAVAILABLE\n",stderr);return 1;}
 struct wl_registry *r=wl_display_get_registry(display);wl_registry_add_listener(r,&listener,NULL);
 if(wl_display_roundtrip(display)<0 || !seat || !pm || !km){fputs("PROTOCOL_UNAVAILABLE\n",stderr);return 1;}
 if(argc==2 && !strcmp(argv[1],"--probe")){puts("{\"protocols_available\":true}");wl_display_disconnect(display);return 0;}
 if(wl_display_roundtrip(display)<0 || seat_count!=1){fputs("AMBIGUOUS_SEAT\n",stderr);return 1;}
 const char *requested=argc==3 && !strcmp(argv[1],"--output")?argv[2]:NULL;
 struct wl_output *selected=NULL;
 for(unsigned i=0;i<output_count;i++) if((requested && !strcmp(requested,outputs[i].name)) || (!requested && output_count==1))selected=outputs[i].handle;
 if(!selected || (output_count>1 && pointer_version<2)){fputs("OUTPUT_MAPPING_UNAVAILABLE\n",stderr);return 1;}
 context=xkb_context_new(0);
 struct xkb_rule_names names={.layout="us"};
 struct xkb_keymap *map=xkb_keymap_new_from_names(context,&names,0);
 if(!map){fputs("KEYMAP_FAILED\n",stderr);return 1;}
 char *text=xkb_keymap_get_as_string(map,XKB_KEYMAP_FORMAT_TEXT_V1);
 base_keymap=strdup(text);
 int fd=memfd_create("wf-keymap",MFD_CLOEXEC);size_t len=strlen(text)+1;
 if(fd<0 || write(fd,text,len)!=(ssize_t)len){fputs("KEYMAP_FAILED\n",stderr);return 1;}
 pointer=pointer_version>=2?zwlr_virtual_pointer_manager_v1_create_virtual_pointer_with_output(pm,seat,selected):zwlr_virtual_pointer_manager_v1_create_virtual_pointer(pm,seat);
 keyboard=zwp_virtual_keyboard_manager_v1_create_virtual_keyboard(km,seat);
 zwp_virtual_keyboard_v1_keymap(keyboard,1,fd,len);close(fd);free(text);
 if(wl_display_roundtrip(display)<0)return 1;
 puts("READY");fflush(stdout);
 char line[256];unsigned a,b,c,d;double value;
 while(fgets(line,sizeof(line),stdin)){
  int valid=1;
  if(sscanf(line,"move %u %u %u %u",&a,&b,&c,&d)==4 && c && d && a<c && b<d) zwlr_virtual_pointer_v1_motion_absolute(pointer,now(),a,b,c,d);
  else if(sscanf(line,"button %u %u",&a,&b)==2 && a>=272 && a<=276 && b<=1){zwlr_virtual_pointer_v1_button(pointer,now(),a,b);buttons[a]=b;}
  else if(sscanf(line,"key %u %u",&a,&b)==2 && a<768 && b<=1){zwp_virtual_keyboard_v1_key(keyboard,now(),a,b);keys[a]=b;}
  else if(sscanf(line,"modifiers %u",&a)==1) zwp_virtual_keyboard_v1_modifiers(keyboard,a,0,0,0);
  else if(sscanf(line,"axis %u %lf",&a,&value)==2 && a<=1 && value>=-10000 && value<=10000) zwlr_virtual_pointer_v1_axis(pointer,now(),a,wl_fixed_from_double(value));
  else if(sscanf(line,"unicode %u",&a)==1) valid=unicode_character(a)>=0;
  else if(!strcmp(line,"release\n"))release();
  else if(!strcmp(line,"stop\n"))break;
  else valid=0;
  if(valid){zwlr_virtual_pointer_v1_frame(pointer);if(wl_display_roundtrip(display)<0)break;}
  puts(valid?"OK":"INVALID_COMMAND");fflush(stdout);
 }
 release();zwp_virtual_keyboard_v1_destroy(keyboard);zwlr_virtual_pointer_v1_destroy(pointer);wl_display_flush(display);
 free(base_keymap);xkb_keymap_unref(map);xkb_context_unref(context);wl_display_disconnect(display);return 0;
}
