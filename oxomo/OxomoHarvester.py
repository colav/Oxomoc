class OxomoHarvester:
    """
    Class for harvesting data from D Space
    """
    def __init__(self,endpoints:dict ,mongo_db="dspace", mongodb_uri="mongodb://localhost:27017/"):
        """
        Harvester constructor
        
        Parameters:
        ----------
        endpoints:dict
            dictionary with dspace endpoint url and university name
        mongodb_uri:str
            MongoDB connection string uri
        """
        self.ckp = OxomoCheckPoint(mongodb_uri)
        self.endpoints = endpoints
        self.mongo_db = mongo_db
        self.client = MongoClient(mongodb_uri)
        self.registry = MetadataRegistry()
        self.registry.registerReader('oai_dc', oai_dc_reader)
    
    def process_record(self,client:Client,identifier:str, mongo_db: str, mongo_collection:str):
        """
        This method perform the request for the given record id and save it in the mongo
        collection and updates the checkpoint collection when it was inserted.
        
        Parameters:
        ---------
        client: oaipmh.client
            oaipmh client instance 
        identifier:str
            record id
        mongo_db:str
            MongoDb name
        mongo_collection:str
            MongoDb collection name
        """
        try:
            raw_record = client.getRecord(identifier=identifier,metadataPrefix='oai_dc')
        except Exception as e:
            record={}
            record["_id"]=identifier
            record["instance"]=str(type(e))
            record["msg"]=str(e)
            self.client[mongo_db][f"{mongo_collection}_errors"].insert_one(record)
            self.ckp.update_record(self.mongo_db, mongo_collection,keys={"_id":identifier})
            print("=== ERROR ===")
            print(e)
            print(identifier)
            return
        
        if raw_record[0].isDeleted():
            record={}
            record["_id"]=identifier
            self.client[mongo_db][f"{mongo_collection}_deleted"].insert_one(record)
            self.ckp.update_record(self.mongo_db, mongo_collection,keys={"_id":identifier})
            print("=== WARNING ===")
            print(f"=== Found deleted record {identifier}")
        else:
            record=raw_record[1].getMap()
            record["_id"]=identifier
            self.client[mongo_db][f"{mongo_collection}_records"].insert_one(record)
            self.ckp.update_record(self.mongo_db, mongo_collection,keys={"_id":identifier})

    def run(self,jobs=None):
        """
        Method to start the harvesting of the data in the multiples endpoints in parallel.
        You have to create the checkpoint first, before call this method.
        
        Parameters:
        ----------
        jobs:int
            number of jobs for parallel execution, if the value is None, it will
            take the number of threads available in the cpu.
        """
        if jobs is None:
            jobs = psutil.cpu_count()
        
        for endpoint in self.endpoints:
            url = endpoint
            mongo_collection = self.endpoints[endpoint]
            print(f"=== Processing {mongo_collection} from {url} ")
            if self.ckp.exists(self.mongo_db, mongo_collection):
                client = Client(url, self.registry)
                record_ids = self.ckp.get_records_regs(self.mongo_db,mongo_collection)
                Parallel(n_jobs=jobs, backend='threading', verbose=10)(delayed(self.process_record)(
                client, record["_id"],self.mongo_db,mongo_collection) for record in record_ids)
            else:
                print(f"*** Error: checkpoint for {url} not found, create it first with ...")
                print(f"*** Omitting {url} {mongo_collection}")