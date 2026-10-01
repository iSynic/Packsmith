#import <Foundation/Foundation.h>
#import "XADSimpleUnarchiver.h"
#include <stdio.h>
#include <locale.h>

@interface ProbeDelegate:NSObject { @public int failures; }
@end
@implementation ProbeDelegate
-(void)simpleUnarchiverNeedsPassword:(XADSimpleUnarchiver *)unarchiver { failures++; }
-(void)simpleUnarchiver:(XADSimpleUnarchiver *)unarchiver didExtractEntryWithDictionary:(NSDictionary *)dict to:(NSString *)path error:(XADError)error {if(error) {failures++;printf("{\"event\":\"entry_error\",\"code\":%d}\n",error);}}
-(BOOL)extractionShouldStopForSimpleUnarchiver:(XADSimpleUnarchiver *)unarchiver {return NO;}
@end

#ifdef _WIN32
#include <wchar.h>
static NSString *argument(const wchar_t *text) {return [NSString stringWithCharacters:(const unichar *)text length:wcslen(text)];}
int wmain(int argc,const wchar_t **argv) {
#else
static NSString *argument(const char *text) {return [NSString stringWithUTF8String:text];}
int main(int argc,const char **argv) {
#endif
    setlocale(LC_ALL,"");
    if(argc<3) return 2;
    NSAutoreleasePool *pool=[NSAutoreleasePool new];
    char buffer[1024];buffer[0]=0;
    if(fgets(buffer,sizeof(buffer),stdin)) buffer[strcspn(buffer,"\r\n")]=0;
    XADError openError;
    XADSimpleUnarchiver *unarchiver=[XADSimpleUnarchiver simpleUnarchiverForPath:argument(argv[1]) error:&openError];
    if(!unarchiver) {printf("{\"event\":\"error\",\"code\":%d}\n",openError);[pool release];return 1;}
    ProbeDelegate *delegate=[ProbeDelegate new];[unarchiver setDelegate:delegate];
    [unarchiver setPassword:[NSString stringWithUTF8String:buffer]];
    memset(buffer,0,sizeof(buffer));
    [unarchiver setDestination:argument(argv[2])];
    [unarchiver setAlwaysOverwritesFiles:YES];[unarchiver setAlwaysSkipsFiles:NO];
    [unarchiver setMacResourceForkStyle:XADHiddenAppleDoubleForkStyle];
    [unarchiver setExtractsSubArchives:YES];
    if(argc>=4) [unarchiver addGlobFilter:argument(argv[3])];
    XADError parseError=[unarchiver parse];
    XADError extractError=parseError ? parseError : [unarchiver unarchive];
    int failures=delegate->failures;
    printf("{\"event\":\"complete\",\"parse_error\":%d,\"extract_error\":%d,\"file_failures\":%d,\"files_extracted\":%d}\n",parseError,extractError,failures,[unarchiver numberOfItemsExtracted]);
    [delegate release];[pool release];return parseError||extractError||failures;
}
