#include <archive.h>
#include <archive_entry.h>
#include <zip.h>
#include <cstdlib>
#include <cstring>
#include <clocale>
#include <fstream>
#include <iostream>
#include <string>

static std::string quote(const char *value) {
    std::string out="\"";
    for (const unsigned char c: std::string(value ? value : "")) {
        if(c=='"'||c=='\\') {out+='\\';out+=c;}
        else if(c<32) {char buf[7];std::snprintf(buf,sizeof(buf),"\\u%04x",c);out+=buf;}
        else out+=c;
    }
    return out+'"';
}
static int error(const char *message) {std::cout<<"{\"event\":\"error\",\"message\":"<<quote(message)<<"}\n";return 1;}
static int cancel(zip_t *, void *) {return std::getenv("ASSESSMENT_CANCEL") ? 1 : 0;}
static void progress(zip_t *, double value, void *) {std::cout<<"{\"event\":\"progress\",\"fraction\":"<<value<<"}\n";}

int main(int argc,char **argv) {
    std::setlocale(LC_ALL,"");
    if(argc<3) return error("operation and archive required");
    const std::string op=argv[1];
    if(op=="versions") {std::cout<<"{\"libarchive\":"<<quote(archive_version_string())<<",\"libzip\":"<<quote(zip_libzip_version())<<"}\n";return 0;}
    std::string password;std::getline(std::cin,password);
    if(op.rfind("zip-",0)==0) {
        int code=0;
        zip_t *z=zip_open(argv[2],op=="zip-create" ? ZIP_CREATE|ZIP_TRUNCATE : 0,&code);
        if(!z) return error("zip_open failed");
        if(!password.empty()) zip_set_default_password(z,password.c_str());
        zip_register_progress_callback_with_state(z,0.1,progress,nullptr,nullptr);
        zip_register_cancel_callback_with_state(z,cancel,nullptr,nullptr);
        if(op=="zip-create"||op=="zip-edit") {
            const std::string text=op=="zip-create" ? "alpha\n" : "replacement\n";
            zip_source_t *s=zip_source_buffer(z,text.data(),text.size(),0);
            zip_int64_t index=zip_file_add(z,"alpha.txt",s,ZIP_FL_OVERWRITE);
            if(index<0) {zip_source_free(s);zip_discard(z);return error("add failed");}
            if(!password.empty() && zip_file_set_encryption(z,index,ZIP_EM_AES_256,password.c_str())) {zip_discard(z);return error("AES encryption failed");}
            if(op=="zip-edit") {
                const auto remove=zip_name_locate(z,"nested/beta.bin",0);
                if(remove>=0 && zip_delete(z,remove)) {zip_discard(z);return error("delete failed");}
                const auto rename=zip_name_locate(z,"unicode/caf\xc3\xa9-\xe6\x97\xa5\xe6\x9c\xac.txt",ZIP_FL_ENC_UTF_8);
                if(rename>=0 && zip_file_rename(z,rename,"renamed.txt",ZIP_FL_ENC_UTF_8)) {zip_discard(z);return error("rename failed");}
                static const char added[]="added\n";
                auto extra=zip_source_buffer(z,added,sizeof(added)-1,0);
                if(zip_file_add(z,"added.txt",extra,0)<0) {zip_source_free(extra);zip_discard(z);return error("extra add failed");}
            }
            if(zip_close(z)) {std::string reason=zip_strerror(z);zip_discard(z);return error(reason.c_str());}
        } else {
            for(zip_uint64_t i=0;i<static_cast<zip_uint64_t>(zip_get_num_entries(z,0));++i) {
                zip_stat_t stat;zip_stat_init(&stat);if(zip_stat_index(z,i,0,&stat)) {zip_discard(z);return error("stat failed");}
                if(op=="zip-test"||op=="zip-extract") {
                    if(op=="zip-extract" && (argc<5||std::string(stat.name)!=argv[4])) continue;
                    zip_file_t *file=zip_fopen_index(z,i,0);if(!file) {zip_discard(z);return error("read/decryption failed");}
                    std::ofstream out;if(op=="zip-extract") out.open(argv[3],std::ios::binary);
                    char buffer[65536];zip_int64_t n;
                    while((n=zip_fread(file,buffer,sizeof(buffer)))>0) {if(out.is_open()) out.write(buffer,n);}
                    bool failed=n<0 || (op=="zip-extract"&&!out.good());zip_fclose(file);
                    if(failed) {zip_discard(z);return error("payload read/write failed");}
                }
                std::cout<<"{\"event\":\"entry\",\"name\":"<<quote(stat.name)<<",\"size\":"<<stat.size<<"}\n";
            }
            zip_discard(z);
        }
    } else if(op=="archive-list"||op=="archive-test"||op=="archive-extract") {
        archive *a=archive_read_new();archive_read_support_filter_all(a);archive_read_support_format_all(a);
        if(!password.empty()) archive_read_add_passphrase(a,password.c_str());
        if(archive_read_open_filename(a,argv[2],65536)!=ARCHIVE_OK) {std::string reason=archive_error_string(a);archive_read_free(a);return error(reason.c_str());}
        archive_entry *e;int result;
        while((result=archive_read_next_header(a,&e))==ARCHIVE_OK) {
            const char *name=archive_entry_pathname_utf8(e);if(!name) name=archive_entry_pathname(e);
            if(op!="archive-list") {
                std::ofstream out;bool selected=op=="archive-extract"&&argc>=5&&std::string(name)==argv[4];
                if(selected) out.open(argv[3],std::ios::binary);
                char buffer[65536];la_ssize_t n;
                while((n=archive_read_data(a,buffer,sizeof(buffer)))>0) {if(selected) out.write(buffer,n);}
                if(n<0||(selected&&!out.good())) {std::string reason=archive_error_string(a)?archive_error_string(a):"write failed";archive_read_free(a);return error(reason.c_str());}
            }
            std::cout<<"{\"event\":\"entry\",\"name\":"<<quote(name)<<",\"size\":"<<archive_entry_size(e)<<"}\n";
        }
        if(result!=ARCHIVE_EOF) {std::string reason=archive_error_string(a);archive_read_free(a);return error(reason.c_str());}
        archive_read_free(a);
    } else return error("unknown operation");
    std::cout<<"{\"event\":\"complete\"}\n";return 0;
}
